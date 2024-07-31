import os
import json
import paramiko
from plexapi.server import PlexServer
from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from retrying import retry
import threading
import time
import logging

app = Flask(__name__)
socketio = SocketIO(app)
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
db = SQLAlchemy(app)

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

CONFIG_FILE = '/app/config.json'
PLEX_USERS_FILE = '/app/plex_users.json'
PRIVATE_KEY_FILE = '/root/.ssh/id_rsa'

logging.basicConfig(level=logging.INFO)

def load_config():
    with open(CONFIG_FILE, 'r') as file:
        return json.load(file)

def ensure_directory_exists(filepath):
    directory = os.path.dirname(filepath)
    if not os.path.exists(directory):
        os.makedirs(directory)

def save_plex_users(data):
    ensure_directory_exists(PLEX_USERS_FILE)
    with open(PLEX_USERS_FILE, 'w') as file:
        json.dump(data, file, indent=4)

def load_plex_users():
    if os.path.exists(PLEX_USERS_FILE):
        with open(PLEX_USERS_FILE, 'r') as file:
            return json.load(file)
    return []

def log(message):
    print(message)
    logging.info(message)

config = load_config()

@retry(stop_max_attempt_number=3, wait_fixed=2000)
def ssh_connect(ip, port, user, timeout=30):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    private_key = paramiko.RSAKey(filename=PRIVATE_KEY_FILE)
    ssh.connect(ip, port=port, username=user, pkey=private_key, timeout=timeout)
    return ssh

def fetch_preferences_via_ssh(ssh, paths):
    preferences = []
    for path in paths:
        stdin, stdout, stderr = ssh.exec_command(f'find "{path}" -maxdepth 6 -type f -name "Preferences.xml"')
        preferences += stdout.read().decode().splitlines()
    return preferences

def extract_url_token(preferences_file, node_ip):
    try:
        with open(preferences_file, 'r') as file:
            content = file.read()
        token = content.split('PlexOnlineToken="')[1].split('"')[0]
        port = content.split('ManualPortMappingPort="')[1].split('"')[0]
        return f"http://{node_ip}:{port}/", token
    except Exception as e:
        log(f"Error extracting URL and token: {e}")
        return None, None

def fetch_file_via_sftp(sftp, remote_path, local_path):
    temp_local_path = local_path + ".tmp"
    try:
        logging.info(f"Starting SFTP transfer from {remote_path} to {temp_local_path}")
        ensure_directory_exists(temp_local_path)
        remote_file_size = sftp.stat(remote_path).st_size
        logging.info(f"Expected remote file size: {remote_file_size}")
        sftp.get(remote_path, temp_local_path)
        local_file_size = os.path.getsize(temp_local_path)
        logging.info(f"Downloaded file size: {local_file_size}")
        if remote_file_size != local_file_size:
            raise IOError(f"Size mismatch in get! {remote_file_size} != {local_file_size}")
        os.rename(temp_local_path, local_path)
        logging.info(f"File transfer completed successfully.")
    except Exception as e:
        logging.error(f"File transfer failed: {e}")
        if os.path.exists(temp_local_path):
            os.remove(temp_local_path)
        raise e

@celery.task
def fetch_plex_servers():
    servers = []
    for node in config['nodes']:
        log(f"Processing node: {node['name']} ({node['ip']})")
        if node['local_access']:
            for path in node['paths']:
                if os.path.isdir(path):
                    for user_dir in os.listdir(path):
                        pref_path = os.path.join(path, user_dir, "Library/Application Support/Plex Media Server/Preferences.xml")
                        if os.path.isfile(pref_path):
                            url, token = extract_url_token(pref_path, node['ip'])
                            if url and token:
                                servers.append({'name': node['name'], 'url': url, 'token': token})
        else:
            ssh = ssh_connect(node['ip'], node['port'], config['SSH_USER'])
            preferences_files = fetch_preferences_via_ssh(ssh, node['paths'])
            for pref_file in preferences_files:
                local_file = os.path.join("/tmp", os.path.basename(pref_file))
                sftp = ssh.open_sftp()
                fetch_file_via_sftp(sftp, pref_file, local_file)
                sftp.close()
                url, token = extract_url_token(local_file, node['ip'])
                if url and token:
                    servers.append({'name': node['name'], 'url': url, 'token': token})
            ssh.close()
    save_plex_users(servers)
    socketio.emit('plex_servers_updated', {'data': servers})
    return servers

@celery.task
def monitor_servers():
    servers = load_plex_users()  # Read from plex_users.json
    data = []
    for server in servers:
        log(f"Connecting to Plex server: {server['url']}")
        try:
            plex = PlexServer(server['url'], server['token'])
            sessions = plex.sessions()
            log(f"Found {len(sessions)} sessions on {server['name']}")
            for session in sessions:
                user = session.usernames[0]
                try:
                    state = session.state
                except AttributeError:
                    state = 'unknown'
                transcode = session.transcodeSession
                video_decision = transcode.videoDecision if transcode else 'Direct Play'
                ip_address = session.players[0].address if session.players else 'unknown'
                media = session.video if hasattr(session, 'video') else None
                if media:
                    poster_url = plex.transcodeImageUrl(media.thumb, width=200)
                    log(f"Session Data: User: {user}, State: {state}, Title: {media.title}, IP: {ip_address}")
                    data.append({
                        'server': server['name'],
                        'user': user,
                        'state': state,
                        'bandwidth': session.bandwidth,
                        'transcode': video_decision,
                        'ip_address': ip_address,
                        'title': media.title,
                        'poster': poster_url,
                        'type': media.type
                    })
        except Exception as e:
            log(f"Error connecting to Plex server {server['name']}: {e}")
    
    log(f"Final Monitor Data: {data}")
    socketio.emit('session_update', {'data': data})
    return data

@app.route('/monitor')
def monitor():
    monitor_servers.delay()  # Run the monitoring task asynchronously
    return jsonify({'status': 'monitoring started'})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    fetch_plex_servers.delay()  # Fetch servers as a background task on startup
    socketio.run(app, host='0.0.0.0', port=5000)
