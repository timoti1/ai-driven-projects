// Unit tests for llama-status session meter logic.
// Runs with Node.js built-in test runner: node --test tests/session.test.ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  newSession,
  fmtSecs,
  isThinkingDelta,
  onInput,
  onToolCall,
  onBeforeProviderRequest,
  onMessageUpdate,
  onToolExecutionStart,
  onToolExecutionEnd,
  onMessageEnd,
  onAgentEnd,
  onSessionShutdown,
  buildSessionMeter,
  type SessionState,
  type Theme,
} from "./session.ts";

const NOW = 1_000_000_000_000; // fixed timestamp for deterministic tests

const THINK = "thinking_delta";
const TEXT = "text_delta";
const TOOLCALL = "toolcall_delta";

const mockTheme: Theme = {
  fg: (_style: string, text: string) => text,
};

function freshSession(): SessionState {
  return newSession();
}

describe("fmtSecs", () => {
  it("formats seconds under a minute", () => {
    assert.strictEqual(fmtSecs(0), "0s");
    assert.strictEqual(fmtSecs(499), "0s");
    assert.strictEqual(fmtSecs(500), "1s");
    assert.strictEqual(fmtSecs(1500), "2s");
    assert.strictEqual(fmtSecs(59000), "59s");
  });

  it("formats minutes and seconds", () => {
    assert.strictEqual(fmtSecs(60000), "1m 0s");
    assert.strictEqual(fmtSecs(91000), "1m 31s");
    assert.strictEqual(fmtSecs(125000), "2m 5s");
  });

  it("formats hours", () => {
    assert.strictEqual(fmtSecs(3600000), "1h 0m 0s");
    assert.strictEqual(fmtSecs(3661000), "1h 1m 1s");
  });
});

describe("isThinkingDelta", () => {
  it("matches thinking_start, thinking_delta, thinking_end", () => {
    assert.strictEqual(isThinkingDelta("thinking_start"), true);
    assert.strictEqual(isThinkingDelta("thinking_delta"), true);
    assert.strictEqual(isThinkingDelta("thinking_end"), true);
  });

  it("rejects text and toolcall deltas", () => {
    assert.strictEqual(isThinkingDelta("text_delta"), false);
    assert.strictEqual(isThinkingDelta("text_start"), false);
    assert.strictEqual(isThinkingDelta("toolcall_delta"), false);
    assert.strictEqual(isThinkingDelta(undefined), false);
    assert.strictEqual(isThinkingDelta(null), false);
  });
});

describe("onInput", () => {
  it("resets all counters and starts session", () => {
    const se = freshSession();
    onInput(se, NOW);
    assert.strictEqual(se.active, true);
    assert.strictEqual(se.startedAt, NOW);
    assert.strictEqual(se.endedAt, null);
    assert.strictEqual(se.toolCalls, 0);
    assert.strictEqual(se.toolFailures, 0);
    assert.strictEqual(se.requests, 0);
    assert.strictEqual(se.ppTime, 0);
    assert.strictEqual(se.reqTime, 0);
    assert.strictEqual(se.toolTime, 0);
    assert.strictEqual(se.thinkTime, 0);
    assert.strictEqual(se.ppStartAt, null);
    assert.strictEqual(se.reqStartAt, null);
    assert.strictEqual(se.ppMeasured, false);
    assert.strictEqual(se.lastDeltaType, null);
    assert.strictEqual(se.lastDeltaTime, null);
    assert.strictEqual(se.toolStart.size, 0);
  });

  it("resets a previously running session", () => {
    const se = freshSession();
    onInput(se, NOW);
    onToolCall(se);
    onBeforeProviderRequest(se, NOW + 1000);
    onMessageUpdate(se, NOW + 2000, THINK);
    onMessageUpdate(se, NOW + 3000, THINK);
    onToolExecutionStart(se, "tc1", NOW + 4000);
    onToolExecutionEnd(se, "tc1", NOW + 5000);
    onMessageEnd(se, NOW + 7000);
    onInput(se, NOW + 10000);
    assert.strictEqual(se.toolCalls, 0);
    assert.strictEqual(se.toolFailures, 0);
    assert.strictEqual(se.requests, 0);
    assert.strictEqual(se.ppTime, 0);
    assert.strictEqual(se.reqTime, 0);
    assert.strictEqual(se.toolTime, 0);
    assert.strictEqual(se.thinkTime, 0);
    assert.strictEqual(se.ppStartAt, null);
    assert.strictEqual(se.reqStartAt, null);
    assert.strictEqual(se.ppMeasured, false);
    assert.strictEqual(se.lastDeltaType, null);
    assert.strictEqual(se.lastDeltaTime, null);
    assert.strictEqual(se.startedAt, NOW + 10000);
  });
});

describe("onToolCall", () => {
  it("increments toolCalls when active", () => {
    const se = freshSession();
    onInput(se, NOW);
    onToolCall(se);
    onToolCall(se);
    assert.strictEqual(se.toolCalls, 2);
  });

  it("ignores toolCall when not active", () => {
    const se = freshSession();
    onToolCall(se);
    assert.strictEqual(se.toolCalls, 0);
  });

  it("initializes toolFailures to 0", () => {
    const se = freshSession();
    assert.strictEqual(se.toolFailures, 0);
  });
});

describe("onBeforeProviderRequest", () => {
  it("increments requests and starts PP timer", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW + 1000);
    assert.strictEqual(se.requests, 1);
    assert.strictEqual(se.ppStartAt, NOW + 1000);
    assert.strictEqual(se.reqStartAt, null);
  });

  it("ignores when not active", () => {
    const se = freshSession();
    onBeforeProviderRequest(se, NOW);
    assert.strictEqual(se.requests, 0);
    assert.strictEqual(se.ppStartAt, null);
  });
});

describe("onMessageUpdate (assistant)", () => {
  it("ends PP timing and starts generation timer on first update", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW); // ppStartAt = NOW
    onMessageUpdate(se, NOW + 3000, TEXT);
    assert.strictEqual(se.ppTime, 3000); // PP = 3s
    assert.strictEqual(se.ppStartAt, null);
    assert.strictEqual(se.ppMeasured, true);
    assert.strictEqual(se.reqStartAt, NOW + 3000);
    assert.strictEqual(se.thinkTime, 0); // first update: no prior interval
  });

  it("only measures PP once (first update)", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 3000, TEXT); // PP measured
    onMessageUpdate(se, NOW + 5000, TEXT); // should not add to PP
    assert.strictEqual(se.ppTime, 3000);
    assert.strictEqual(se.ppMeasured, true);
  });

  it("accumulates thinking time for thinking deltas", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // first: no interval
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    onMessageUpdate(se, NOW + 5000, THINK); // +2s thinking
    assert.strictEqual(se.thinkTime, 4000);
  });

  it("does not count text/toolcall intervals as thinking", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, TEXT); // first
    onMessageUpdate(se, NOW + 3000, TEXT); // +2s generation
    onMessageUpdate(se, NOW + 5000, TOOLCALL); // +2s generation
    assert.strictEqual(se.thinkTime, 0);
  });

  it("ignores when not active", () => {
    const se = freshSession();
    onMessageUpdate(se, NOW + 1000, TEXT);
    assert.strictEqual(se.ppTime, 0);
    assert.strictEqual(se.reqStartAt, null);
    assert.strictEqual(se.thinkTime, 0);
  });
});

describe("onToolExecutionStart / onToolExecutionEnd", () => {
  it("tracks tool time correctly", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onToolExecutionEnd(se, "tc1", NOW + 5000); // 4s tool
    assert.strictEqual(se.toolTime, 4000);
    assert.ok(se.toolTime > 0, `toolTime should be > 0, got ${se.toolTime}`);
  });

  it("handles multiple tools sequentially", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onToolExecutionEnd(se, "tc1", NOW + 3000); // tool: 2s
    onToolExecutionStart(se, "tc2", NOW + 4000);
    onToolExecutionEnd(se, "tc2", NOW + 7000); // tool: 3s
    assert.strictEqual(se.toolTime, 5000); // 2s + 3s
  });

  it("ignores unknown toolCallId on end", () => {
    const se = freshSession();
    onInput(se, NOW);
    onToolExecutionEnd(se, "nonexistent", NOW + 1000);
    assert.strictEqual(se.toolTime, 0);
    assert.strictEqual(se.toolFailures, 0);
  });

  it("counts failed tool calls", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onToolExecutionEnd(se, "tc1", NOW + 3000, true); // failed
    assert.strictEqual(se.toolFailures, 1);
  });

  it("counts multiple failed tool calls", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onToolExecutionEnd(se, "tc1", NOW + 2000, true); // failed
    onToolExecutionStart(se, "tc2", NOW + 3000);
    onToolExecutionEnd(se, "tc2", NOW + 5000); // success
    onToolExecutionStart(se, "tc3", NOW + 6000);
    onToolExecutionEnd(se, "tc3", NOW + 7000, true); // failed
    assert.strictEqual(se.toolFailures, 2);
    assert.strictEqual(se.toolTime, 4000); // 1s + 2s + 1s = 4s
  });

  it("ignores when not active", () => {
    const se = freshSession();
    onToolExecutionStart(se, "tc1", NOW);
    onToolExecutionEnd(se, "tc1", NOW + 1000);
    assert.strictEqual(se.toolTime, 0);
  });
});

describe("onMessageEnd", () => {
  it("accumulates reqTime from first update to message_end", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, TEXT); // PP = 1s, req starts
    onToolExecutionStart(se, "tc1", NOW + 2000);
    onToolExecutionEnd(se, "tc1", NOW + 3000); // tool: 1s
    onMessageEnd(se, NOW + 6000); // req = 5s
    // reqTime = NOW+6000 - (NOW+1000) = 5000 = 5s
    assert.strictEqual(se.reqTime, 5000);
    assert.strictEqual(se.reqStartAt, null);
    assert.strictEqual(se.ppTime, 1000); // PP = 1s
    assert.strictEqual(se.thinkTime, 0); // only one update, no thinking interval
  });

  it("closes the final thinking interval", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // first
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    onMessageEnd(se, NOW + 5000); // final interval +2s thinking
    assert.strictEqual(se.thinkTime, 4000);
    assert.strictEqual(se.reqTime, 4000); // NOW+1000 to NOW+5000
  });

  it("ignores when not active", () => {
    const se = freshSession();
    onMessageEnd(se, NOW + 1000);
    assert.strictEqual(se.reqTime, 0);
  });

  it("ignores when no pending request", () => {
    const se = freshSession();
    onInput(se, NOW);
    onMessageEnd(se, NOW + 1000);
    assert.strictEqual(se.reqTime, 0);
  });
});

describe("onAgentEnd", () => {
  it("freezes session and finalizes all timing", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW + 1000);
    onMessageUpdate(se, NOW + 2000, TEXT); // PP = 1s
    onToolExecutionStart(se, "tc1", NOW + 3000);
    onToolExecutionEnd(se, "tc1", NOW + 4000); // tool: 1s
    onAgentEnd(se, NOW + 5000); // req = 3s (NOW+2000 to NOW+5000)
    assert.strictEqual(se.active, false);
    assert.strictEqual(se.endedAt, NOW + 5000);
    assert.strictEqual(se.ppTime, 1000); // 1s
    assert.strictEqual(se.reqTime, 3000); // 3s
    assert.strictEqual(se.toolTime, 1000); // 1s
    assert.strictEqual(se.reqStartAt, null);
    assert.strictEqual(se.ppStartAt, null);
  });

  it("finalizes in-flight thinking at agent_end", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // first
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    onAgentEnd(se, NOW + 5000); // final interval +2s thinking
    assert.strictEqual(se.thinkTime, 4000);
    assert.strictEqual(se.reqTime, 4000);
  });

  it("ignores when not active", () => {
    const se = freshSession();
    onAgentEnd(se, NOW + 1000);
    assert.strictEqual(se.active, false);
    assert.strictEqual(se.endedAt, null);
  });

  it("finalizes in-flight tool at agent_end", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onAgentEnd(se, NOW + 5000);
    assert.strictEqual(se.toolTime, 4000); // NOW+1000 to NOW+5000
    assert.strictEqual(se.reqTime, 5000); // NOW to NOW+5000
    assert.strictEqual(se.ppTime, 0);
  });

  it("finalizes unmeasured PP at agent_end", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    // No message_update ever fired — PP counts up to agent_end
    onAgentEnd(se, NOW + 5000);
    assert.strictEqual(se.ppTime, 5000);
    assert.strictEqual(se.ppMeasured, false);
  });
});

describe("onSessionShutdown", () => {
  it("resets session to initial state", () => {
    const se = freshSession();
    onInput(se, NOW);
    onToolCall(se);
    onBeforeProviderRequest(se, NOW + 1000);
    onMessageUpdate(se, NOW + 2000, THINK);
    onMessageEnd(se, NOW + 3000);
    onSessionShutdown(se);
    assert.strictEqual(se.active, false);
    assert.strictEqual(se.startedAt, null);
    assert.strictEqual(se.toolCalls, 0);
    assert.strictEqual(se.toolFailures, 0);
    assert.strictEqual(se.requests, 0);
    assert.strictEqual(se.ppTime, 0);
    assert.strictEqual(se.reqTime, 0);
    assert.strictEqual(se.toolTime, 0);
    assert.strictEqual(se.thinkTime, 0);
    assert.strictEqual(se.toolStart.size, 0);
    assert.strictEqual(se.ppMeasured, false);
    assert.strictEqual(se.lastDeltaType, null);
    assert.strictEqual(se.lastDeltaTime, null);
  });
});

describe("buildSessionMeter", () => {
  it("returns empty string when session not started", () => {
    const se = freshSession();
    assert.strictEqual(buildSessionMeter(mockTheme, se, NOW), "");
  });

  it("formats meter string with req/think/gen", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW + 1000); // PP starts at NOW+1000
    onMessageUpdate(se, NOW + 2000, THINK); // PP = 1s, req starts, first update
    onMessageUpdate(se, NOW + 4000, THINK); // +2s thinking
    onMessageUpdate(se, NOW + 6000, TEXT); // +2s generation
    onMessageEnd(se, NOW + 8000); // final interval +2s generation; req = 6s
    // ppTime = 1000 = 1s
    // reqTime = 6000 = 6s
    // thinkTime = 2000 = 2s
    // gen = reqTime - thinkTime = 6000 - 2000 = 4000 = 4s
    // toolTime = 0
    // up = NOW+8000 - NOW = 8000 = 8s
    const result = buildSessionMeter(mockTheme, se, NOW + 8000);
    assert.match(result, new RegExp('last prompt: up 8s  \\(PP: 1s, req\\/think\\/gen: 6s\\/2s\\/4s, tool calls: 0s\\)  calls\\/failures 0\\/0  req 1'));
  });

  it("uses endedAt when session is not active", () => {
    const se = freshSession();
    onInput(se, NOW);
    onAgentEnd(se, NOW + 3000);
    const result = buildSessionMeter(mockTheme, se, NOW + 10000);
    assert.match(result, /up 3s/);
  });

  it("req/think/gen stream live during an active request (no underflow)", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // first: PP=1s, req starts, no interval
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    // Mid-stream render at NOW+4000 (1s after last token, still thinking).
    // liveReq = 0 + (NOW+4000 - reqStartAt(NOW+1000)) = 3000
    // liveThink = thinkTime(2000) + (NOW+4000 - lastDeltaTime(NOW+3000)) = 3000
    // gen = max(0, 3000 - 3000) = 0 ; think <= req holds
    const result = buildSessionMeter(mockTheme, se, NOW + 4000);
    assert.match(result, /req\/think\/gen: 3s\/3s\/0s/);
  });

  it("think never exceeds req while streaming (no underflow)", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK);
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    onMessageUpdate(se, NOW + 5000, THINK); // +2s thinking
    // Mid-stream render at NOW+6000 (1s after last token, still thinking).
    // liveReq = 0 + (NOW+6000 - reqStartAt(NOW+1000)) = 5000
    // liveThink = thinkTime(4000) + (NOW+6000 - lastDeltaTime(NOW+5000)) = 5000
    // gen = 0 ; think == req (no more think > req)
    const result = buildSessionMeter(mockTheme, se, NOW + 6000);
    assert.match(result, /req\/think\/gen: 5s\/5s\/0s/);
  });

  it("gen grows live as text tokens stream", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // first, thinking
    onMessageUpdate(se, NOW + 3000, TEXT); // +2s generation
    onMessageUpdate(se, NOW + 5000, TEXT); // +2s generation
    // Render at NOW+5000 (right at last token).
    // liveReq = 0 + (NOW+5000 - reqStartAt(NOW+1000)) = 4000
    // liveThink = 0 (interval attributed to TEXT, not thinking)
    // gen = max(0, 4000 - 0) = 4000
    const result = buildSessionMeter(mockTheme, se, NOW + 5000);
    assert.match(result, /req\/think\/gen: 4s\/0s\/4s/);
  });

  it("PP streams live during prefill", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW); // PP starts at NOW, no tokens yet
    // Still in prefill. Render at NOW+3000.
    // livePP = ppTime(0) + (NOW+3000 - ppStartAt(NOW)) = 3000
    const result = buildSessionMeter(mockTheme, se, NOW + 3000);
    assert.match(result, /PP: 3s/);
  });

  it("values are frozen after message_end (no in-flight portion)", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK);
    onMessageUpdate(se, NOW + 3000, TEXT); // +2s generation
    onMessageEnd(se, NOW + 5000); // closes req, clears lastDelta
    // After message_end: reqStartAt=null, lastDeltaType=null.
    // Render at NOW+9000 (well after).
    // liveReq = reqTime(4000) + 0 = 4000
    // liveThink = thinkTime(0) + 0 = 0
    // gen = 4000
    const result = buildSessionMeter(mockTheme, se, NOW + 9000);
    assert.match(result, /req\/think\/gen: 4s\/0s\/4s/);
  });
});

describe("integration: full prompt flow", () => {
  it("PP + reqTime + toolTime tracked separately", () => {
    const se = freshSession();
    onInput(se, NOW);
    // PP: 2s, then req: 4s with 1s tool inside
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 2000, TEXT); // PP = 2s
    onToolExecutionStart(se, "tc1", NOW + 3000);
    onToolExecutionEnd(se, "tc1", NOW + 4000); // tool = 1s
    onMessageEnd(se, NOW + 6000); // req = 4s
    assert.strictEqual(se.ppTime, 2000);
    assert.strictEqual(se.reqTime, 4000);
    assert.strictEqual(se.toolTime, 1000);
    assert.ok(se.reqTime >= se.toolTime);
  });

  it("gen = req - think, and think is a subset of req", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, THINK); // PP = 1s, first
    onMessageUpdate(se, NOW + 3000, THINK); // +2s thinking
    onMessageUpdate(se, NOW + 5000, TEXT); // +2s generation
    onMessageEnd(se, NOW + 7000); // final +2s generation; req = 6s
    assert.strictEqual(se.reqTime, 6000);
    assert.strictEqual(se.thinkTime, 2000);
    const gen = se.reqTime - se.thinkTime;
    assert.strictEqual(gen, 4000);
    assert.ok(se.thinkTime <= se.reqTime, `think(${se.thinkTime}) <= req(${se.reqTime})`);
  });

  it("tool execution is separate from req (not subtracted from it)", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW + 1000, TEXT); // PP = 1s, req starts
    onMessageEnd(se, NOW + 3000); // req = 2s
    onToolExecutionStart(se, "tc1", NOW + 3500);
    onToolExecutionEnd(se, "tc1", NOW + 5500); // tool = 2s, OUTSIDE req window
    onBeforeProviderRequest(se, NOW + 6000);
    onMessageUpdate(se, NOW + 7000, TEXT); // PP = 1s, req starts
    onMessageEnd(se, NOW + 9000); // req = 2s
    assert.strictEqual(se.reqTime, 4000); // 2s + 2s
    assert.strictEqual(se.toolTime, 2000); // separate
    // gen = req - think = 4000 - 0 = 4000 (not reduced by toolTime)
    const gen = se.reqTime - se.thinkTime;
    assert.strictEqual(gen, 4000);
  });

  it("multiple requests accumulate correctly", () => {
    const se = freshSession();
    onInput(se, NOW);
    // Request 1: PP=1s, req=4s, tool=2s
    onBeforeProviderRequest(se, NOW + 1000);
    onMessageUpdate(se, NOW + 2000, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 3000);
    onToolExecutionEnd(se, "tc1", NOW + 5000);
    onMessageEnd(se, NOW + 6000);
    // Request 2: PP=2s, req=3s, tool=0s
    onBeforeProviderRequest(se, NOW + 7000);
    onMessageUpdate(se, NOW + 9000, TEXT);
    onMessageEnd(se, NOW + 12000);
    assert.strictEqual(se.requests, 2);
    assert.strictEqual(se.ppTime, 3000); // 1s + 2s
    assert.strictEqual(se.reqTime, 7000); // 4s + 3s
    assert.strictEqual(se.toolTime, 2000); // 2s
    assert.ok(se.reqTime >= se.toolTime);
    assert.ok(se.reqTime > se.toolTime);
  });

  it("tool time is not zero when tools execute", () => {
    const se = freshSession();
    onInput(se, NOW);
    onBeforeProviderRequest(se, NOW);
    onMessageUpdate(se, NOW, TEXT);
    onToolExecutionStart(se, "tc1", NOW + 1000);
    onToolExecutionEnd(se, "tc1", NOW + 3000);
    onToolExecutionStart(se, "tc2", NOW + 4000);
    onToolExecutionEnd(se, "tc2", NOW + 7000);
    onMessageEnd(se, NOW + 10000);
    assert.strictEqual(se.toolTime, 5000); // 2s + 3s
    assert.ok(se.toolTime > 0, `toolTime should be > 0, got ${se.toolTime}`);
    assert.ok(se.reqTime > se.toolTime, `reqTime(${se.reqTime}) > toolTime(${se.toolTime})`);
  });
});
