# Prints admit() over every (Fresh, Used, Pace, Who) in nested order, then route(True), route(False).
# tests/burn_pace/test_burn_pace_twin.py compares it with lib/z0/burn_pace.py admit_cls / route_cls.
import Base
import ./MODEL.bend as M

def main() -> List<Bool>:
  [M.admit(M.FFresh{}, M.UUnder{}, M.PCool{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UUnder{}, M.PCool{}, M.WBulk{}),
   M.admit(M.FFresh{}, M.UUnder{}, M.PUnknown{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UUnder{}, M.PUnknown{}, M.WBulk{}),
   M.admit(M.FFresh{}, M.UUnder{}, M.PHot{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UUnder{}, M.PHot{}, M.WBulk{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PCool{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PCool{}, M.WBulk{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PUnknown{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PUnknown{}, M.WBulk{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PHot{}, M.WOwner{}),
   M.admit(M.FFresh{}, M.UAtCap{}, M.PHot{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PCool{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PCool{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PUnknown{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PUnknown{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PHot{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UUnder{}, M.PHot{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PCool{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PCool{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PUnknown{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PUnknown{}, M.WBulk{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PHot{}, M.WOwner{}),
   M.admit(M.FStale{}, M.UAtCap{}, M.PHot{}, M.WBulk{}),
   M.is_paid(M.route(True{})),
   M.is_paid(M.route(False{}))]
