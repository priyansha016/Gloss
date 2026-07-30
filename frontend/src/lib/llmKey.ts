/**
 * Bring-your-own-key storage.
 *
 * The key lives in this browser's localStorage and is sent only as a header on
 * the requests that need it. Gloss never stores it server-side, which is the
 * promise made in the UI — so don't add logging or a "save to profile" path here.
 */

export type ProviderId = "groq" | "gemini" | "openai";

export type ProviderInfo = {
  id: ProviderId;
  label: string;
  /** Where the user generates a key. */
  consoleUrl: string;
  /** What the key looks like, to catch a pasted wrong thing early. */
  keyPrefix: string;
  hint: string;
  free: boolean;
};

export const PROVIDERS: ProviderInfo[] = [
  {
    id: "groq",
    label: "Groq",
    consoleUrl: "https://console.groq.com/keys",
    keyPrefix: "gsk_",
    hint: "Free tier, fastest. Recommended.",
    free: true,
  },
  {
    id: "gemini",
    label: "Google Gemini",
    consoleUrl: "https://aistudio.google.com/apikey",
    keyPrefix: "AIza",
    hint: "Free tier, generous daily limits.",
    free: true,
  },
  {
    id: "openai",
    label: "OpenAI",
    consoleUrl: "https://platform.openai.com/api-keys",
    keyPrefix: "sk-",
    hint: "Paid — you're billed per video.",
    free: false,
  },
];

const KEY_STORAGE = "gloss.llm.key";
const PROVIDER_STORAGE = "gloss.llm.provider";

export type StoredKey = {
  provider: ProviderId;
  key: string;
};

export function loadKey(): StoredKey | null {
  if (typeof window === "undefined") return null;
  try {
    const key = window.localStorage.getItem(KEY_STORAGE);
    const provider = window.localStorage.getItem(PROVIDER_STORAGE) as ProviderId | null;
    if (!key || !provider) return null;
    if (!PROVIDERS.some((p) => p.id === provider)) return null;
    return { provider, key };
  } catch {
    return null; // private mode / storage disabled
  }
}

export function saveKey(stored: StoredKey): void {
  try {
    window.localStorage.setItem(KEY_STORAGE, stored.key.trim());
    window.localStorage.setItem(PROVIDER_STORAGE, stored.provider);
  } catch {
    // Non-fatal: the key still works for this page's lifetime via the caller.
  }
  notify();
}

export function clearKey(): void {
  try {
    window.localStorage.removeItem(KEY_STORAGE);
    window.localStorage.removeItem(PROVIDER_STORAGE);
  } catch {
    // ignore
  }
  notify();
}

/** Headers for a request that spends tokens. Empty when the user has no key. */
export function keyHeaders(): Record<string, string> {
  const stored = loadKey();
  if (!stored) return {};
  return { "X-LLM-Key": stored.key, "X-LLM-Provider": stored.provider };
}

export function maskKey(key: string): string {
  const trimmed = key.trim();
  if (trimmed.length <= 8) return "••••";
  return `${trimmed.slice(0, 4)}••••${trimmed.slice(-4)}`;
}

export function providerInfo(id: ProviderId): ProviderInfo {
  return PROVIDERS.find((p) => p.id === id) ?? PROVIDERS[0];
}

// Components in different subtrees (header badge, modal, doc page) show key state,
// so changes broadcast instead of being lifted into a shared provider.
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function subscribeToKey(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
