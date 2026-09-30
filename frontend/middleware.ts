import { NextResponse, type NextRequest } from "next/server";

// Streamed chat answers must reach the browser event by event. Next gzips responses,
// including the /api rewrite to FastAPI, and a gzipped event stream arrives in one piece
// once the answer is finished. Asking for an identity encoding on this one path keeps it
// streaming; every other response stays compressed. The request itself is unchanged.
export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("accept-encoding", "identity");
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: "/api/v1/chat" };
