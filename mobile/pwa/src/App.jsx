/**
 * ARGUS PWA — Main App
 * Mobile-first dashboard for field officers (Sarpanchs, NDRF, SDMA).
 * Features: offline detection, village selection, push notification prompt.
 */
import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { loadSavedVillage, saveVillageToIDB } from './db';

const FieldDashboard     = lazy(() => import('./components/FieldDashboard'));
const VillageSelector    = lazy(() => import('./components/VillageSelector'));
const ReportFlood        = lazy(() => import('./components/ReportFlood'));
const EvacuationCard     = lazy(() => import('./components/EvacuationCard'));
const NotificationPrompt = lazy(() => import('./components/NotificationPrompt'));

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-screen bg-argus-bg">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full border-4 border-argus-border border-t-argus-accent animate-spin" />
        <span className="text-argus-muted text-sm font-exo2">Loading ARGUS…</span>
      </div>
    </div>
  );
}

export default function App() {
  const [online, setOnline]     = useState(navigator.onLine);
  const [village, setVillage]   = useState(null);
  const [loading, setLoading]   = useState(true);
  const navigate = useNavigate();

  // Online/offline detection
  useEffect(() => {
    const goOnline  = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener('online',  goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online',  goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  // Restore saved village from IndexedDB
  useEffect(() => {
    loadSavedVillage()
      .then((saved) => {
        if (saved) setVillage(saved);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const selectVillage = useCallback(async (v) => {
    setVillage(v);
    await saveVillageToIDB(v);
    navigate('/');
  }, [navigate]);

  const clearVillage = useCallback(async () => {
    setVillage(null);
    await saveVillageToIDB(null);
    navigate('/select');
  }, [navigate]);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="min-h-screen bg-argus-bg text-argus-text font-exo2 safe-top safe-bottom">
      {/* Offline banner */}
      {!online && (
        <div className="sticky top-0 z-50 bg-argus-orange/90 text-black text-center text-xs font-semibold py-1 px-2">
          ⚠ Offline — showing cached data
        </div>
      )}

      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route
            path="/"
            element={
              village
                ? <FieldDashboard village={village} online={online} onChangeVillage={clearVillage} />
                : <Navigate to="/select" replace />
            }
          />
          <Route
            path="/select"
            element={<VillageSelector onSelect={selectVillage} />}
          />
          <Route
            path="/report"
            element={
              village
                ? <ReportFlood village={village} online={online} />
                : <Navigate to="/select" replace />
            }
          />
          <Route
            path="/evacuation"
            element={
              village
                ? <EvacuationCard village={village} online={online} />
                : <Navigate to="/select" replace />
            }
          />
          <Route
            path="/notifications"
            element={
              village
                ? <NotificationPrompt village={village} />
                : <Navigate to="/select" replace />
            }
          />
        </Routes>
      </Suspense>
    </div>
  );
}
