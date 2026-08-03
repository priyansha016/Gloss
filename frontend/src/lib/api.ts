import { keyHeaders } from "./llmKey";

const DEFAULT_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let resolvedApiUrl: string | null = null;
let apiUrlPromise: Promise<string> | null = null;

function isDeployedSite(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.hostname.endsWith(".workers.dev");
}

/** API base URL. On workers.dev the Worker proxies /api — same origin, no config.json. */
export async function getApiUrl(): Promise<string> {
  if (resolvedApiUrl) return resolvedApiUrl;
  if (!apiUrlPromise) {
    apiUrlPromise = (async () => {
      if (typeof window !== "undefined" && isDeployedSite()) {
        resolvedApiUrl = window.location.origin.replace(/\/$/, "");
        return resolvedApiUrl;
      }
      if (typeof window !== "undefined") {
        try {
          const res = await fetch("/config.json", { cache: "no-store" });
          if (res.ok) {
            const cfg = (await res.json()) as { apiUrl?: string };
            if (cfg.apiUrl?.trim()) {
              resolvedApiUrl = cfg.apiUrl.trim().replace(/\/$/, "");
              return resolvedApiUrl;
            }
          }
        } catch {
          /* local fallback */
        }
      }
      resolvedApiUrl = DEFAULT_API_URL.replace(/\/$/, "");
      return resolvedApiUrl;
    })();
  }
  return apiUrlPromise;
}

/** Thrown when the backend requires the user's own API key (HTTP 428). */
export class UserKeyRequiredError extends Error {
  constructor() {
    super("Add your own AI API key to continue.");
    this.name = "UserKeyRequiredError";
  }
}

export function isUserKeyRequired(err: unknown): boolean {
  return err instanceof UserKeyRequiredError;
}

export type SubmitVideoResponse = {
  video_id: string;
  job_id: string | null;
  cached: boolean;
  status: string;
};

export type JobResponse = {
  id: string;
  video_id: string;
  state: string;
  error: string | null;
  progress: string | null;
  video_status: string;
  created_at: string;
  updated_at: string;
};

export type TranscriptSegment = {
  start_s: number;
  end_s: number;
  text: string;
};

export type WalkStep = {
  text: string;
  math: string;
  code: string;
};

export type VisualStep = {
  caption: string;
  math: string;
  diagram: string;
};

export type VisualBlock = {
  focus: string;
  steps: VisualStep[];
};

export type SectionContent = {
  headline: string;
  explainer: string;
  key_points: string[];
  walkthrough: WalkStep[];
  diagram: string;
  visual?: VisualBlock | null;
};

export type Section = {
  id: string;
  idx: number;
  title: string;
  start_s: number;
  end_s: number;
  summary_short: string | null;
  summary_full: string | null;
  content: SectionContent | null;
};

export type NavItem = {
  t: number;
  label: string;
  one_liner: string;
};

export type Command = {
  cmd: string;
  purpose: string;
};

export type NoteGroup = {
  heading: string;
  bullets: string[];
};

export type QAItem = {
  question: string;
  answer: string;
  kind: "understanding" | "interview";
};

export type Flashcard = {
  front: string;
  back: string;
};

export type QuizQuestion = {
  question: string;
  options: string[];
  answer: number;
  explanation: string;
};

export type DocOverview = {
  teaches: string;
  prerequisites: string[];
  nav: NavItem[];
  summary: string[];
  concept_map: string;
  commands: Command[];
  notes: NoteGroup[];
  qa: QAItem[];
  // Present only after the user generates them (cached thereafter)
  flashcards?: Flashcard[];
  quiz?: QuizQuestion[];
};

export type GlossaryTerm = {
  id: string;
  term: string;
  display: string;
  definition_beginner: string;
  domain: string | null;
};

export type VideoDocument = {
  id: string;
  youtube_id: string;
  title: string | null;
  channel: string | null;
  duration_s: number | null;
  lang: string | null;
  status: string;
  progress: string | null;
  status_reason: string | null;
  tldr: string | null;
  overview: DocOverview | null;
  sections: Section[];
  raw_segments: TranscriptSegment[];
  cleaned_segments: TranscriptSegment[];
  glossary: GlossaryTerm[];
  term_occurrences: { term_id: string; section_id: string | null; segment_idx: number | null }[];
};

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  /** Send the user's own API key: only for calls that spend LLM tokens. */
  opts?: { withKey?: boolean },
): Promise<T> {
  const base = await getApiUrl();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(opts?.withKey ? keyHeaders() : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    if (res.status === 428) throw new UserKeyRequiredError();
    const body = await res.text();
    throw new Error(body || `Request failed: ${res.status}`);
  }

  return res.json() as Promise<T>;
}

export async function submitVideo(url: string, forceReprocess = false): Promise<SubmitVideoResponse> {
  return apiFetch<SubmitVideoResponse>(
    "/api/videos",
    {
      method: "POST",
      body: JSON.stringify({ url, force_reprocess: forceReprocess }),
    },
    { withKey: true },
  );
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/jobs/${jobId}`);
}

export async function getVideo(videoId: string): Promise<VideoDocument> {
  return apiFetch<VideoDocument>(`/api/videos/${videoId}`);
}

export type AskSource = { title: string; start_s: number };
export type AskResponse = { answer: string; sources: AskSource[] };
export type AskTurn = { role: "user" | "assistant"; content: string };

export async function askQuestion(
  videoId: string,
  question: string,
  history: AskTurn[] = [],
): Promise<AskResponse> {
  return apiFetch<AskResponse>(
    `/api/videos/${videoId}/ask`,
    {
      method: "POST",
      body: JSON.stringify({ question, history: history.slice(-12) }),
    },
    { withKey: true },
  );
}

export type PracticeResponse = {
  kind: "flashcards" | "quiz";
  cards: Flashcard[];
  questions: QuizQuestion[];
  cached: boolean;
};

export async function generatePractice(
  videoId: string,
  kind: "flashcards" | "quiz",
): Promise<PracticeResponse> {
  return apiFetch<PracticeResponse>(
    `/api/videos/${videoId}/practice`,
    {
      method: "POST",
      body: JSON.stringify({ kind }),
    },
    { withKey: true },
  );
}

export type ShowcaseVideo = {
  id: string;
  youtube_id: string;
  title: string | null;
  channel: string | null;
  duration_s: number | null;
};

export type AdminStats = {
  videos_total: number;
  videos_ready: number;
  videos_processing: number;
  videos_failed: number;
  jobs_completed: number;
  jobs_failed: number;
  llm_calls: number;
  llm_tokens: number;
  recent_videos: ShowcaseVideo[];
};

export async function getShowcase(): Promise<ShowcaseVideo[]> {
  return apiFetch<ShowcaseVideo[]>("/api/showcase");
}

const ADMIN_KEY_STORAGE = "gloss.admin.key";

export function loadAdminKey(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(ADMIN_KEY_STORAGE);
  } catch {
    return null;
  }
}

export function saveAdminKey(key: string): void {
  window.sessionStorage.setItem(ADMIN_KEY_STORAGE, key.trim());
}

export function clearAdminKey(): void {
  window.sessionStorage.removeItem(ADMIN_KEY_STORAGE);
}

export async function getAdminStats(adminKey: string): Promise<AdminStats> {
  return apiFetch<AdminStats>("/api/admin/stats", {
    headers: { "X-Admin-Key": adminKey },
  });
}

export function pollJobUntilDone(
  jobId: string,
  onTick?: (job: JobResponse) => void,
  intervalMs = 2000,
): Promise<JobResponse> {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const job = await getJob(jobId);
        onTick?.(job);
        if (job.state === "completed" || job.state === "failed") {
          resolve(job);
          return;
        }
        setTimeout(tick, intervalMs);
      } catch (err) {
        reject(err);
      }
    };
    tick();
  });
}
