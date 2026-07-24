/**
 * NotificationPrompt — Push notification opt-in / management screen.
 * Uses the Web Push API + Notification Hub service.
 */
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { subscribeToPushNotifications, fetchAlertHistory } from '../api';

const VAPID_PUBLIC_KEY = import.meta.env.VITE_VAPID_PUBLIC_KEY || '';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

export default function NotificationPrompt({ village }) {
  const [permission, setPermission] = useState(Notification.permission);
  const [subscribed, setSubscribed] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [history, setHistory]       = useState([]);
  const [error, setError]           = useState(null);

  // Fetch alert history on mount
  useEffect(() => {
    fetchAlertHistory(village.id)
      .then((data) => setHistory(Array.isArray(data) ? data : data.alerts || []))
      .catch(() => {});
  }, [village.id]);

  // Check existing subscription
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then((reg) => {
        reg.pushManager.getSubscription().then((sub) => {
          if (sub) setSubscribed(true);
        });
      });
    }
  }, []);

  const handleSubscribe = async () => {
    setSubscribing(true);
    setError(null);
    try {
      const result = await Notification.requestPermission();
      setPermission(result);
      if (result !== 'granted') {
        setError('Notification permission denied');
        return;
      }

      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });

      await subscribeToPushNotifications(sub.toJSON(), village.id);
      setSubscribed(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubscribing(false);
    }
  };

  const alertColor = (level) => {
    const map = { NORMAL: 'text-green-400', WATCH: 'text-yellow-400', WARNING: 'text-orange-400', DANGER: 'text-red-400', EMERGENCY: 'text-red-600' };
    return map[level] || 'text-argus-muted';
  };

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="bg-argus-card border-b border-argus-border px-4 py-3 flex items-center gap-3">
        <Link to="/" className="text-argus-accent">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div>
          <h1 className="text-lg font-bold">Alert Notifications</h1>
          <p className="text-xs text-argus-muted">{village.name}</p>
        </div>
      </header>

      <main className="flex-1 p-4 space-y-4 overflow-y-auto">
        {/* Subscription card */}
        <section className="bg-argus-card rounded-xl p-4 shadow">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 shrink-0 rounded-full bg-argus-accent/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-argus-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0" />
              </svg>
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-semibold">Push Notifications</h2>
              <p className="text-xs text-argus-muted mt-0.5">
                Get instant alerts when flood risk changes for {village.name}
              </p>

              {!subscribed ? (
                <button
                  onClick={handleSubscribe}
                  disabled={subscribing || permission === 'denied'}
                  className="mt-3 w-full py-2.5 rounded-lg bg-argus-accent text-white font-semibold text-sm disabled:opacity-40 transition"
                >
                  {subscribing
                    ? 'Enabling…'
                    : permission === 'denied'
                      ? 'Notifications Blocked'
                      : 'Enable Alert Notifications'}
                </button>
              ) : (
                <div className="mt-3 flex items-center gap-2 text-green-400 text-sm">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  Notifications active
                </div>
              )}

              {permission === 'denied' && (
                <p className="text-xs text-red-400 mt-1">
                  Please enable notifications in your browser settings.
                </p>
              )}
            </div>
          </div>
        </section>

        {error && (
          <div className="bg-red-900/30 border border-red-600 rounded-lg p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Alert History */}
        <section className="bg-argus-card rounded-xl p-4 shadow">
          <h2 className="text-sm font-semibold text-argus-accent mb-3">Recent Alerts</h2>
          {history.length === 0 ? (
            <p className="text-sm text-argus-muted">No recent alerts</p>
          ) : (
            <ul className="space-y-3">
              {history.slice(0, 20).map((alert, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  <span className={`mt-0.5 font-bold ${alertColor(alert.level)}`}>●</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`font-semibold ${alertColor(alert.level)}`}>
                        {alert.level}
                      </span>
                      <span className="text-xs text-argus-muted whitespace-nowrap">
                        {alert.timestamp ? new Date(alert.timestamp).toLocaleDateString() : ''}
                      </span>
                    </div>
                    {alert.message && (
                      <p className="text-xs text-argus-muted mt-0.5 truncate">{alert.message}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Info */}
        <p className="text-xs text-argus-muted text-center px-4">
          Alerts are sent via ARGUS push notification service when your village's
          risk level changes to WATCH or above.
        </p>
      </main>
    </div>
  );
}
