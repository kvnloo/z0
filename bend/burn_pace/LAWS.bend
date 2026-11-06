# Owner laws for burn_pace: respect each subscription's pace by moving bulk work to free lanes
# automatically, while the owner keeps the premium model in their own conversation.
# Universally quantified over MODEL's domains.
# Not proven here: that the twin classifies readings and callers correctly (parity test) or that
# the running gateway loads the twin (deployment receipt).
import Base
import ./MODEL.bend as M

# A stale or missing reading never admits a paid row, for anyone (fail closed).
law stale_never_admits:
  for u: M.Used
  for p: M.Pace
  for w: M.Who
  {M.admit(M.FStale{}, u, p, w) == False{} : Bool}

# A row at its weekly cap never serves, not even the owner's own chat.
law at_cap_never_admits:
  for f: M.Fresh
  for p: M.Pace
  for w: M.Who
  {M.admit(f, M.UAtCap{}, p, w) == False{} : Bool}

# Bulk work (subagents, lanes, aux) never uses a row that is over pace.
law hot_bulk_never_admits:
  for f: M.Fresh
  for u: M.Used
  {M.admit(f, u, M.PHot{}, M.WBulk{}) == False{} : Bool}

# The owner keeps the premium model while a fresh row is under cap, even when it is over pace.
law owner_keeps_opus_when_hot:
  {M.admit(M.FFresh{}, M.UUnder{}, M.PHot{}, M.WOwner{}) == True{} : Bool}

# Non-vacuity: fresh, under-cap, cool or unreported rows admit bulk work.
law fresh_cool_admits:
  {M.admit(M.FFresh{}, M.UUnder{}, M.PCool{}, M.WBulk{}) == True{} : Bool}

law fresh_unknown_admits:
  {M.admit(M.FFresh{}, M.UUnder{}, M.PUnknown{}, M.WBulk{}) == True{} : Bool}

# When no paid row is admitted the turn goes to the free lane, never to a drained row.
law none_admitted_routes_free:
  {M.route(False{}) == M.RFree{} : M.Route}

law admitted_routes_paid:
  {M.route(True{}) == M.RPaid{} : M.Route}

# Composition: bulk work on a hot row routes free.
law hot_bulk_routes_free:
  for f: M.Fresh
  for u: M.Used
  {M.route(M.admit(f, u, M.PHot{}, M.WBulk{})) == M.RFree{} : M.Route}
