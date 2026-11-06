# burn_pace: may one subscription pool row serve the next request, and where does the
# turn go when no row may? Operational twin: lib/z0/burn_pace.py (classify + admit_cls), loaded by Hermes
# CredentialPool._available_entries via agent/burn_pace_gate.py. tests/burn_pace/
# test_twin.py runs every row of these finite domains through the twin.
# Reading burn-pace samples and mapping labels to lanes happen in the twin, not here.
import Base

# The latest burn-pace reading is at most STALE_S old.
type Fresh is Data:
  FFresh{}
  FStale{}

# Weekly window below USED_STOP (95%) or at/over it.
type Used is Data:
  UUnder{}
  UAtCap{}

# Pace ratio below RATIO_STOP (1.5), unreported, or at/over it.
type Pace is Data:
  PCool{}
  PUnknown{}
  PHot{}

# Who is asking: the owner's own conversation on the premium model in an owner profile, or anything else
# (lane profiles, subagents, auxiliary calls, cron).
type Who is Data:
  WOwner{}
  WBulk{}

# Where the turn goes: a paid subscription row, or the free lane (fallback_providers).
type Route is Data:
  RPaid{}
  RFree{}

def pace_ok(p: Pace) -> Bool:
  match p:
    case PCool{}:
      True{}
    case PUnknown{}:
      True{}
    case PHot{}:
      False{}

def pace_ok_for(w: Who, p: Pace) -> Bool:
  match w:
    case WOwner{}:
      True{}
    case WBulk{}:
      pace_ok(p)

def admit(f: Fresh, u: Used, p: Pace, w: Who) -> Bool:
  match f:
    case FFresh{}:
      match u:
        case UUnder{}:
          pace_ok_for(w, p)
        case UAtCap{}:
          False{}
    case FStale{}:
      False{}

def route(any_admitted: Bool) -> Route:
  match any_admitted:
    case True{}:
      RPaid{}
    case False{}:
      RFree{}

def is_paid(r: Route) -> Bool:
  match r:
    case RPaid{}:
      True{}
    case RFree{}:
      False{}
