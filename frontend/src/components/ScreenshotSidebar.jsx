import React, { useEffect, useState, useRef, useCallback } from "react";
import { apiService } from "../services/api";

const POLL_INTERVAL = 1500;

function formatTime(mtime) {
    const d = new Date(mtime * 1000);
    return d.toLocaleTimeString();
}

export default function ScreenshotSidebar() {
    const [screenshots, setScreenshots] = useState([]);
    const [error, setError] = useState(null);
    const [lightbox, setLightbox] = useState(null);
    const pollingRef = useRef(null);

    const fetchScreenshots = useCallback(async () => {
        try {
            const data = await apiService.listScreenshots();
            const next = data.screenshots || [];
            setScreenshots(prev => {
                if (prev.length === next.length &&
                    prev.every((p, i) => p.filename === next[i].filename)) {
                    return prev;
                }
                return next;
            });
            setError(null);
        } catch (err) {
            setError(err.message || "Failed to load screenshots");
        }
    }, []);

    useEffect(() => {
        fetchScreenshots();
        pollingRef.current = setInterval(fetchScreenshots, POLL_INTERVAL);
        return () => clearInterval(pollingRef.current);
    }, [fetchScreenshots]);

    return (
        <>
            <aside className="hidden lg:flex fixed top-16 right-4 bottom-4 w-80
                bg-white dark:bg-gray-900 rounded shadow-md flex-col overflow-hidden
                border border-gray-200 dark:border-gray-700">
                <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700
                    flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                        Screenshots
                    </h2>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                        {screenshots.length}
                    </span>
                </div>
                <div className="flex-grow overflow-y-auto p-3 space-y-3">
                    {error && (
                        <div className="text-xs text-red-500">{error}</div>
                    )}
                    {!error && screenshots.length === 0 && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            No screenshots yet.
                        </div>
                    )}
                    {screenshots.map(shot => (
                        <button
                            key={shot.filename}
                            onClick={() => setLightbox(shot)}
                            className="block w-full text-left group"
                            aria-label={`Open ${shot.filename}`}
                        >
                            <img
                                src={apiService.getScreenshotUrl(shot.filename)}
                                alt={shot.filename}
                                loading="lazy"
                                className="w-full rounded border border-gray-200
                                    dark:border-gray-700 group-hover:border-blue-500
                                    transition-colors"
                            />
                            <div className="mt-1 text-[10px] text-gray-500 dark:text-gray-400
                                truncate">
                                {formatTime(shot.mtime)} · {shot.filename}
                            </div>
                        </button>
                    ))}
                </div>
            </aside>

            {lightbox && (
                <div
                    role="dialog"
                    aria-modal="true"
                    onClick={() => setLightbox(null)}
                    className="fixed inset-0 z-50 bg-black/80 flex items-center
                        justify-center p-6 cursor-zoom-out"
                >
                    <img
                        src={apiService.getScreenshotUrl(lightbox.filename)}
                        alt={lightbox.filename}
                        className="max-w-full max-h-full rounded shadow-2xl"
                    />
                </div>
            )}
        </>
    );
}
