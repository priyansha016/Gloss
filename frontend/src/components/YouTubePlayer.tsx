"use client";

import { useEffect, useRef } from "react";

type YtPlayer = {
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  playVideo?: () => void;
  getIframe?: () => HTMLIFrameElement;
  destroy?: () => void;
};

declare global {
  interface Window {
    YT?: {
      Player: new (
        element: HTMLElement,
        options: Record<string, unknown>,
      ) => YtPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

type YouTubePlayerProps = {
  youtubeId: string;
  startSeconds?: number;
  /** Increments on every jump click, so repeated clicks (even same time) always seek. */
  seekNonce?: number;
  title?: string;
};

export function YouTubePlayer({ youtubeId, startSeconds = 0, seekNonce = 0, title }: YouTubePlayerProps) {
  const targetRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YtPlayer | null>(null);
  const readyRef = useRef(false);
  // A click can land before the player is ready — remember it and apply on ready.
  const pendingSeekRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const create = () => {
      if (cancelled || !targetRef.current || playerRef.current || !window.YT?.Player) return;
      playerRef.current = new window.YT.Player(targetRef.current, {
        videoId: youtubeId,
        playerVars: { rel: 0 },
        events: {
          onReady: () => {
            readyRef.current = true;
            const iframe = playerRef.current?.getIframe?.();
            if (iframe) {
              iframe.classList.add("absolute", "inset-0", "h-full", "w-full");
              if (title) iframe.title = title;
            }
            if (pendingSeekRef.current != null) {
              playerRef.current?.seekTo(pendingSeekRef.current, true);
              playerRef.current?.playVideo?.();
              pendingSeekRef.current = null;
            }
          },
        },
      });
    };

    if (window.YT?.Player) {
      create();
    } else {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        prev?.();
        create();
      };
      if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        const script = document.createElement("script");
        script.src = "https://www.youtube.com/iframe_api";
        document.head.appendChild(script);
      }
    }

    return () => {
      cancelled = true;
      readyRef.current = false;
      playerRef.current?.destroy?.();
      playerRef.current = null;
    };
  }, [youtubeId, title]);

  // Real seek on every jump click — no iframe reload, starts playing at the timestamp.
  useEffect(() => {
    if (seekNonce === 0) return; // initial mount, no click yet
    if (readyRef.current && playerRef.current?.seekTo) {
      playerRef.current.seekTo(startSeconds, true);
      playerRef.current.playVideo?.();
    } else {
      pendingSeekRef.current = startSeconds;
    }
  }, [startSeconds, seekNonce]);

  return (
    <div className="overflow-hidden rounded-2xl border border-ink-200 bg-black shadow-lg">
      <div className="relative aspect-video w-full">
        <div ref={targetRef} className="absolute inset-0 h-full w-full" />
      </div>
    </div>
  );
}
