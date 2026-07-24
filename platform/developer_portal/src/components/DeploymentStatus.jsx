/**
 * DeploymentStatus — Live deployment progress and status display.
 *
 * Shows the sandbox deployment pipeline stages after a user clicks
 * "Deploy to Playground" in the developer portal.
 */
import { useState, useEffect, useRef } from 'react';

const API_BASE = import.meta.env.VITE_PORTAL_API || 'http://localhost:5175';

const STAGES = [
  { key: 'validate',  label: 'Validating YAML' },
  { key: 'provision',  label: 'Provisioning sandbox' },
  { key: 'model_init', label: 'Initialising model' },
  { key: 'connect',    label: 'Connecting data feeds' },
  { key: 'ready',      label: 'Deployment ready' },
];

function StageIcon({ status }) {
  if (status === 'completed') {
    return (
      <svg className="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
    );
  }
  if (status === 'in-progress') {
    return (
      <div className="w-5 h-5 rounded-full border-2 border-sky-400 border-t-transparent animate-spin" />
    );
  }
  if (status === 'failed') {
    return (
      <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
      </svg>
    );
  }
  return <div className="w-5 h-5 rounded-full border-2 border-slate-600" />;
}

export default function DeploymentStatus({ deploymentId, onComplete, onError }) {
  const [stages, setStages] = useState(
    STAGES.map((s) => ({ ...s, status: 'pending' }))
  );
  const [error, setError] = useState(null);
  const [sandboxUrl, setSandboxUrl] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    if (!deploymentId) return;

    // Reset stages
    setStages(STAGES.map((s) => ({ ...s, status: 'pending' })));
    setError(null);
    setSandboxUrl(null);

    // Poll deployment status
    const poll = async () => {
      try {
        const resp = await fetch(
          `${API_BASE}/api/v1/playground/status/${deploymentId}`
        );
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        // Update stage statuses
        setStages((prev) =>
          prev.map((stage) => ({
            ...stage,
            status: data.stages?.[stage.key] || stage.status,
          }))
        );

        if (data.status === 'ready') {
          setSandboxUrl(data.sandbox_url || null);
          onComplete?.(data);
          clearInterval(pollRef.current);
        } else if (data.status === 'failed') {
          setError(data.error || 'Deployment failed');
          onError?.(data.error);
          clearInterval(pollRef.current);
        }
      } catch (err) {
        setError(err.message);
        onError?.(err.message);
        clearInterval(pollRef.current);
      }
    };

    // Initial check then poll every 2s
    poll();
    pollRef.current = setInterval(poll, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [deploymentId, onComplete, onError]);

  if (!deploymentId) return null;

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700">
        <h3 className="text-sm font-semibold text-slate-100">
          Deployment Progress
        </h3>
        <p className="text-xs text-slate-400 mt-0.5 font-mono">
          {deploymentId}
        </p>
      </div>

      {/* Stages */}
      <div className="p-4 space-y-3">
        {stages.map((stage, i) => (
          <div key={stage.key} className="flex items-center gap-3">
            <StageIcon status={stage.status} />
            <div className="flex-1">
              <div
                className={`text-sm ${
                  stage.status === 'completed'
                    ? 'text-green-400'
                    : stage.status === 'in-progress'
                      ? 'text-sky-400 font-semibold'
                      : stage.status === 'failed'
                        ? 'text-red-400'
                        : 'text-slate-500'
                }`}
              >
                {stage.label}
              </div>
            </div>
            {/* Connector line */}
            {i < stages.length - 1 && (
              <div className="absolute left-[1.625rem] mt-8 w-0.5 h-3 bg-slate-700" />
            )}
          </div>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-4 p-3 bg-red-900/30 border border-red-800/50 rounded-lg text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Success */}
      {sandboxUrl && (
        <div className="mx-4 mb-4 p-3 bg-emerald-900/30 border border-emerald-800/50 rounded-lg">
          <p className="text-sm text-emerald-300 font-semibold mb-1">
            Sandbox Ready
          </p>
          <a
            href={sandboxUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-sky-400 hover:text-sky-300 underline font-mono break-all"
          >
            {sandboxUrl}
          </a>
        </div>
      )}
    </div>
  );
}
