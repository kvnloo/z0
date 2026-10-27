# z0 keepworking kernel: may the main agent stop, or must it keep working?
# Owner ask: "write bend laws to force yourself to keep working until all of the
# asks are at 100% or everything you can do is done, except for only blocked reqs."
# The operational twin is lib/z0/keepworking/kernel.py. Each decide_* below is a
# small finite function; tests/keepworking/test_kernel_twin.py runs every row of
# every domain through both. Reading the ledger and the hook input is not proven here.
import Base

# The status an ask entry claims in ~/workspace/.z0/asks.yaml.
type Status is Data:
  SOpen{}
  SPartial{}
  SDone{}
  SBlocked{}
  SUnknown{}

# What the done evidence names. Owner-visible: a deployed sha, a device receipt,
# or an open/merged PR. Weak: a branch, a spec, green tests, a plan. None: empty.
type Evidence is Data:
  EvNone{}
  EvWeak{}
  EvOwnerVisible{}

# What blocked_by names. Owner-only: sudo, a login, a merge review, a physical step.
type Blocker is Data:
  BkNone{}
  BkAgentDoable{}
  BkOwnerOnly{}

type Ledger is Data:
  LOk{}
  LMissing{}
  LInvalid{}

type Reason is Data:
  RUnbound{}
  RWaitBackground{}
  RAllClear{}
  RNoProgress{}
  ROpenAsks{}
  RLedgerBroken{}

type Verdict is Data:
  VAllow{reason: Reason}
  VBlock{reason: Reason}

# An entry permits stopping only when it is done with owner-visible evidence,
# or blocked on a fresh owner-only reason. Open, partial and unknown never permit it.
def entry_ok(s: Status, ev: Evidence, bk: Blocker, fresh: Bool) -> Bool:
  match s:
    case SOpen{}:
      False{}
    case SPartial{}:
      False{}
    case SUnknown{}:
      False{}
    case SDone{}:
      match ev:
        case EvNone{}:
          False{}
        case EvWeak{}:
          False{}
        case EvOwnerVisible{}:
          True{}
    case SBlocked{}:
      match bk:
        case BkNone{}:
          False{}
        case BkAgentDoable{}:
          False{}
        case BkOwnerOnly{}:
          fresh

# What a stop forbidden by the ledger becomes: a block, unless the hook already
# continued this turn and no tool ran since (loop guard).
def forbid(reason: Reason, active: Bool, progress: Bool) -> Verdict:
  match active:
    case False{}:
      VBlock{reason}
    case True{}:
      match progress:
        case True{}:
          VBlock{reason}
        case False{}:
          VAllow{RNoProgress{}}

def ledger_verdict(ledger: Ledger, all_ok: Bool, active: Bool, progress: Bool) -> Verdict:
  match ledger:
    case LMissing{}:
      forbid(RLedgerBroken{}, active, progress)
    case LInvalid{}:
      forbid(RLedgerBroken{}, active, progress)
    case LOk{}:
      match all_ok:
        case True{}:
          VAllow{RAllClear{}}
        case False{}:
          forbid(ROpenAsks{}, active, progress)

# bound: this session is under the law. waiting: background tasks or session crons
# will wake the session, so a stop is a pause, not an end.
def decide_stop(bound: Bool, waiting: Bool, ledger: Ledger, all_ok: Bool, active: Bool, progress: Bool) -> Verdict:
  match bound:
    case False{}:
      VAllow{RUnbound{}}
    case True{}:
      match waiting:
        case True{}:
          VAllow{RWaitBackground{}}
        case False{}:
          ledger_verdict(ledger, all_ok, active, progress)

def is_block(v: Verdict) -> Bool:
  match v:
    case VAllow{reason}:
      False{}
    case VBlock{reason}:
      True{}

def reason_code(r: Reason) -> Nat:
  match r:
    case RUnbound{}:
      0n
    case RWaitBackground{}:
      1n
    case RAllClear{}:
      2n
    case RNoProgress{}:
      3n
    case ROpenAsks{}:
      4n
    case RLedgerBroken{}:
      5n

def code_verdict(v: Verdict) -> Nat:
  match v:
    case VAllow{reason}:
      reason_code(reason)
    case VBlock{reason}:
      (100n + reason_code(reason) : Nat)

def code_bool(b: Bool) -> Nat:
  match b:
    case False{}:
      0n
    case True{}:
      1n
