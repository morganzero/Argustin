import React, { useState, useEffect } from 'react';
import io from 'socket.io-client';
import 'bootstrap/dist/css/bootstrap.min.css';

const socket = io('http://localhost:5000');

function App() {
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    socket.on('session_update', (data) => {
      setSessions(data.data);
    });

    socket.on('plex_servers_updated', (data) => {
      console.log('Plex servers updated:', data.data);
    });

    return () => {
      socket.off('session_update');
      socket.off('plex_servers_updated');
    };
  }, []);

  return (
    <div className="container mt-4">
      <h1 className="text-center">Argus: Multi-Plex Monitor</h1>
      <div className="row">
        {sessions.length === 0 ? (
          <p className="text-center">No active sessions found.</p>
        ) : (
          sessions.map((session, index) => (
            <div key={index} className="col-md-4">
              <div className="card mb-4">
                <img src={session.poster} className="card-img-top" alt={session.title} />
                <div className="card-body">
                  <h5 className="card-title">{session.title}</h5>
                  <p className="card-text">User: {session.user}</p>
                  <p className="card-text">State: {session.state}</p>
                  <p className="card-text">IP Address: {session.ip_address}</p>
                  <p className="card-text">Transcode: {session.transcode}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default App;
