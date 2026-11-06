// Extracted session meter logic from llama-status extension.
// Pure, dependency-free: no pi APIs, no external packages.
export interface SessionState {
  startedAt: number | null;
  endedAt: number | null;
  active: boolean;
  toolCalls: number;
  toolFailures: number;
  requests: number;
  ppTime: number;
  reqTime: number;
  toolTime: number;
  thinkTime: number;
  ppStartAt: number | null;
  reqStartAt: number | null;
  ppMeasured: boolean;
  lastDeltaType: string | null;
  lastDeltaTime: number | null;
  toolStart: Map<string, number>;
}

export function newSession(): SessionState {
  return {
    startedAt: null, endedAt: null, active: false,
    toolCalls: 0, toolFailures: 0, requests: 0,
    ppTime: 0, reqTime: 0, toolTime: 0, thinkTime: 0,
    ppStartAt: null, reqStartAt: null, ppMeasured: false,
    lastDeltaType: null, lastDeltaTime: null,
    toolStart: new Map(),
  };
}

export function fmtSecs(ms: number): string {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${total}s`;
}

// A delta is a reasoning token if its type is thinking_start/_delta/_end.
export function isThinkingDelta(type: string | null | undefined): boolean {
  return type != null && type.startsWith("thinking");
}

export function onInput(se: SessionState, now: number): void {
  se.startedAt = now;
  se.endedAt = null;
  se.active = true;
  se.toolCalls = 0;
  se.toolFailures = 0;
  se.requests = 0;
  se.ppTime = 0;
  se.reqTime = 0;
  se.toolTime = 0;
  se.thinkTime = 0;
  se.ppStartAt = null;
  se.reqStartAt = null;
  se.ppMeasured = false;
  se.lastDeltaType = null;
  se.lastDeltaTime = null;
  se.toolStart.clear();
}

export function onToolCall(se: SessionState): void {
  if (!se.active) return;
  se.toolCalls++;
}

export function onBeforeProviderRequest(se: SessionState, now: number): void {
  if (!se.active) return;
  se.requests++;
  se.ppStartAt = now;
  se.ppMeasured = false;
}

// message_update fires for each assistant token. The first one marks the end
// of PP (prefill) and the start of generation. message_start fires too early
// (before prefill), so we use message_update instead.
//
// Each inter-delta interval is attributed to the CURRENT delta's type: the
// time from the previous delta to this one is how long THIS token took to
// generate. Thinking deltas accumulate into thinkTime; the rest (text +
// tool-call tokens) is generation.
export function onMessageUpdate(se: SessionState, now: number, deltaType?: string): void {
  if (!se.active) return;
  if (se.ppStartAt != null && !se.ppMeasured) {
    se.ppTime += now - se.ppStartAt;
    se.ppStartAt = null;
    se.ppMeasured = true;
  }
  if (se.reqStartAt == null) {
    se.reqStartAt = now;
  }
  if (se.lastDeltaTime != null && isThinkingDelta(deltaType)) {
    se.thinkTime += now - se.lastDeltaTime;
  }
  se.lastDeltaTime = now;
  se.lastDeltaType = deltaType ?? null;
}

export function onToolExecutionStart(se: SessionState, toolCallId: string, now: number): void {
  if (!se.active) return;
  se.toolStart.set(toolCallId, now);
}

export function onToolExecutionEnd(se: SessionState, toolCallId: string, now: number, isError?: boolean): void {
  if (!se.active) return;
  const start = se.toolStart.get(toolCallId);
  if (start != null) {
    se.toolTime += now - start;
    se.toolStart.delete(toolCallId);
  }
  if (isError) {
    se.toolFailures++;
  }
}

// message_end fires when the assistant message is fully rendered — generation is complete.
// Close the per-request timer and the final inter-delta interval.
export function onMessageEnd(se: SessionState, now: number): void {
  if (!se.active) return;
  if (se.lastDeltaTime != null && isThinkingDelta(se.lastDeltaType)) {
    se.thinkTime += now - se.lastDeltaTime;
  }
  if (se.reqStartAt != null) {
    se.reqTime += now - se.reqStartAt;
    se.reqStartAt = null;
  }
  se.lastDeltaTime = null;
  se.lastDeltaType = null;
}

export function onAgentEnd(se: SessionState, now: number): void {
  if (!se.active) return;
  se.active = false;
  se.endedAt = now;
  if (se.ppStartAt != null && !se.ppMeasured) {
    se.ppTime += now - se.ppStartAt;
    se.ppStartAt = null;
  }
  // Close the final inter-delta interval if the agent ended mid-stream.
  if (se.lastDeltaTime != null && isThinkingDelta(se.lastDeltaType)) {
    se.thinkTime += now - se.lastDeltaTime;
  }
  if (se.reqStartAt != null) {
    se.reqTime += now - se.reqStartAt;
    se.reqStartAt = null;
  }
  se.lastDeltaTime = null;
  se.lastDeltaType = null;
  for (const [, start] of se.toolStart) {
    se.toolTime += now - start;
  }
  se.toolStart.clear();
}

export function onSessionShutdown(se: SessionState): void {
  Object.assign(se, newSession());
}

export interface Theme {
  fg: (style: string, text: string) => string;
}

// req = total generation window (first token -> message_end), which includes
// reasoning + text + tool-call tokens. think = reasoning time (directly
// measured, a subset of req). gen = req - think = text + tool-call writing.
// tool = actual tool execution (between requests, NOT inside req).
export function buildSessionMeter(theme: Theme, se: SessionState, now: number): string {
  if (!se.startedAt) return "";
  const ended = se.active ? now : (se.endedAt ?? se.startedAt);
  const up = fmtSecs(Math.max(0, ended - se.startedAt));
  // Live values: add the in-flight portion of the active request so the
  // numbers stream as tokens arrive. req grows as tokens stream; think grows
  // as thinking tokens stream; pp grows during prefill. Without this, req is
  // frozen until message_end and gen = req - think underflows to 0 mid-stream.
  const livePP = se.ppTime + (se.ppStartAt != null ? now - se.ppStartAt : 0);
  const liveReq = se.reqTime + (se.reqStartAt != null ? now - se.reqStartAt : 0);
  const liveThink = se.thinkTime + (se.lastDeltaTime != null && isThinkingDelta(se.lastDeltaType) ? now - se.lastDeltaTime : 0);
  const pp = fmtSecs(livePP);
  const req = fmtSecs(liveReq);
  const think = fmtSecs(liveThink);
  const gen = fmtSecs(Math.max(0, liveReq - liveThink));
  const tool = fmtSecs(se.toolTime);
  const dim = (s: string) => theme.fg("dim", s);
  return `last prompt: ${dim("up")} ${up}  ${dim("(PP:")} ${pp}, ${dim("req/think/gen:")} ${req}/${think}/${gen}, ${dim("tool calls:")} ${tool})  ${dim("calls/failures")} ${se.toolCalls}/${se.toolFailures}  ${dim("req")} ${se.requests}`;
}
