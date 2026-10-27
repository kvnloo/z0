# All proofs implement the exact, owner-reviewed LAWS.bend signatures.
# Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def Laws.open_entry_forbids(ev, bk, f):
  {==}

def Laws.partial_entry_forbids(ev, bk, f):
  {==}

def Laws.unknown_entry_forbids(ev, bk, f):
  {==}

def Laws.done_without_evidence_forbids(bk, f):
  {==}

def Laws.done_with_weak_evidence_forbids(bk, f):
  {==}

def Laws.done_with_owner_visible_evidence_permits(bk, f):
  {==}

def Laws.blocked_without_reason_forbids(ev, f):
  {==}

def Laws.blocked_on_agent_work_forbids(ev, f):
  {==}

def Laws.stale_block_forbids(ev):
  {==}

def Laws.fresh_owner_block_permits(ev):
  {==}

def Laws.open_asks_block(p):
  {==}

def Laws.open_asks_block_while_progressing(a):
  match a:
    case True{}:
      {==}
    case False{}:
      {==}

def Laws.all_clear_permits(a, p):
  {==}

def Laws.missing_ledger_blocks(ok, p):
  {==}

def Laws.invalid_ledger_blocks(ok, p):
  {==}

def Laws.waiting_permits(l, ok, a, p):
  {==}

def no_progress_ok(ok: Bool) -> {M.is_block(M.ledger_verdict(M.LOk{}, ok, True{}, False{})) == False{} : Bool}:
  match ok:
    case True{}:
      {==}
    case False{}:
      {==}

def Laws.no_progress_loop_guard(l, ok):
  match l:
    case M.LOk{}:
      no_progress_ok(ok)
    case M.LMissing{}:
      {==}
    case M.LInvalid{}:
      {==}

def Laws.unbound_never_blocks(w, l, ok, a, p):
  {==}
