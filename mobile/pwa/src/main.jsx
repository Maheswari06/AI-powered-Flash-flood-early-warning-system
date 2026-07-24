import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

// Register service worker via workbox-window
import { Workbox } from 'workbox-window';

if ('serviceWorker' in navigator) {
  const wb = new Workbox('/pwa/sw.js');

  wb.addEventListener('waiting', () => {
    // New version available — auto-activate for field officers
    wb.messageSkipWaiting();
  });

  wb.addEventListener('controlling', () => {
    window.location.reload();
  });

  wb.register();
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename="/pwa">
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
