/**
 * Cloudflare Worker: static export + proxy /api/* to the Mac backend tunnel.
 * BACKEND_URL = Worker secret (see scripts/demo-up.sh).
 */
export interface Env {
  ASSETS: Fetcher;
  BACKEND_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api")) {
      const backend = env.BACKEND_URL?.trim().replace(/\/$/, "");
      if (!backend) {
        return new Response(
          JSON.stringify({ detail: "Backend not configured. Run ./scripts/demo-up.sh" }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }
      const target = new URL(url.pathname + url.search, backend);
      const headers = new Headers(request.headers);
      headers.delete("host");
      return fetch(
        new Request(target.toString(), {
          method: request.method,
          headers,
          body: request.body,
          redirect: "follow",
        }),
      );
    }

    return env.ASSETS.fetch(request);
  },
};
