# Owner laws for z0 keepworking, universally quantified over MODEL's domains.
# Law: stop is permitted iff every ask is done-with-evidence or
# blocked-with-owner-only-reason. Unknown, partial or stale entries forbid stopping.
# Two owner-requested exits are stated as laws too: background work that will wake
# the session (W1), and the stop_hook_active loop guard when no tool ran (G1).
# No theorem here verifies the ledger contents, the hook input or the transcript.
import Base
import ./MODEL.bend as M

# E1: open, partial and unknown entries never permit a stop.
law open_entry_forbids:
  for ev: M.Evidence
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SOpen{}, ev, bk, f) == False{} : Bool}

law partial_entry_forbids:
  for ev: M.Evidence
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SPartial{}, ev, bk, f) == False{} : Bool}

law unknown_entry_forbids:
  for ev: M.Evidence
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SUnknown{}, ev, bk, f) == False{} : Bool}

# E2: done without owner-visible evidence (a branch, a spec, green tests) is not done.
law done_without_evidence_forbids:
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SDone{}, M.EvNone{}, bk, f) == False{} : Bool}

law done_with_weak_evidence_forbids:
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SDone{}, M.EvWeak{}, bk, f) == False{} : Bool}

law done_with_owner_visible_evidence_permits:
  for bk: M.Blocker
  for f: Bool
  {M.entry_ok(M.SDone{}, M.EvOwnerVisible{}, bk, f) == True{} : Bool}

# E3: blocked is valid only on an owner-only reason, and only while fresh.
law blocked_without_reason_forbids:
  for ev: M.Evidence
  for f: Bool
  {M.entry_ok(M.SBlocked{}, ev, M.BkNone{}, f) == False{} : Bool}

law blocked_on_agent_work_forbids:
  for ev: M.Evidence
  for f: Bool
  {M.entry_ok(M.SBlocked{}, ev, M.BkAgentDoable{}, f) == False{} : Bool}

law stale_block_forbids:
  for ev: M.Evidence
  {M.entry_ok(M.SBlocked{}, ev, M.BkOwnerOnly{}, False{}) == False{} : Bool}

law fresh_owner_block_permits:
  for ev: M.Evidence
  {M.entry_ok(M.SBlocked{}, ev, M.BkOwnerOnly{}, True{}) == True{} : Bool}

# S1: a bound session with a valid ledger and any entry not ok is blocked
# on its first stop attempt.
law open_asks_block:
  for p: Bool
  {M.decide_stop(True{}, False{}, M.LOk{}, False{}, False{}, p) == M.VBlock{M.ROpenAsks{}} : M.Verdict}

# S1: ...and keeps being blocked while it makes progress (a tool ran since the last block).
law open_asks_block_while_progressing:
  for a: Bool
  {M.decide_stop(True{}, False{}, M.LOk{}, False{}, a, True{}) == M.VBlock{M.ROpenAsks{}} : M.Verdict}

# S2: every entry ok permits the stop, whatever the hook state.
law all_clear_permits:
  for a: Bool
  for p: Bool
  {M.decide_stop(True{}, False{}, M.LOk{}, True{}, a, p) == M.VAllow{M.RAllClear{}} : M.Verdict}

# S3: a missing or unparseable ledger is unknown state, so it forbids stopping.
law missing_ledger_blocks:
  for ok: Bool
  for p: Bool
  {M.decide_stop(True{}, False{}, M.LMissing{}, ok, False{}, p) == M.VBlock{M.RLedgerBroken{}} : M.Verdict}

law invalid_ledger_blocks:
  for ok: Bool
  for p: Bool
  {M.decide_stop(True{}, False{}, M.LInvalid{}, ok, False{}, p) == M.VBlock{M.RLedgerBroken{}} : M.Verdict}

# W1: background work that will wake the session makes a stop a pause.
law waiting_permits:
  for l: M.Ledger
  for ok: Bool
  for a: Bool
  for p: Bool
  {M.decide_stop(True{}, True{}, l, ok, a, p) == M.VAllow{M.RWaitBackground{}} : M.Verdict}

# G1: loop guard. A continued turn that ran no tool may stop (honors stop_hook_active).
law no_progress_loop_guard:
  for l: M.Ledger
  for ok: Bool
  {M.is_block(M.decide_stop(True{}, False{}, l, ok, True{}, False{})) == False{} : Bool}

# B1: an unbound session (opted out, or outside the ledger's scope) is never blocked.
law unbound_never_blocks:
  for w: Bool
  for l: M.Ledger
  for ok: Bool
  for a: Bool
  for p: Bool
  {M.decide_stop(False{}, w, l, ok, a, p) == M.VAllow{M.RUnbound{}} : M.Verdict}
