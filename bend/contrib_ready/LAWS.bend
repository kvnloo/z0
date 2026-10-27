# Owner laws for contrib_ready (contributor spec §4.4), universally quantified over
# MODEL's domains and over every matrix (Cells), not only the REQUIRED-length ones.
# No theorem here verifies that a receipt is genuine, that its cell really ran, or
# that the twin read the right directory: those rest on the receipt store and CI.
import Base
import ./MODEL.bend as M

# R1: when any cell of the matrix does not count, the result is never SReady,
# whatever comes before or after it and whatever the blocker.
law uncounted_cell_never_ready:
  for pre: M.Cells
  for r: M.Req
  for c: M.Cell
  for post: M.Cells
  for b: M.Blocker
  for h: {M.counts(c) == False{} : Bool}
  {M.is_ready(M.decide(M.append(pre, M.KCell{r, c, post}), b)) == False{} : Bool}

# R1, by name: a missing, failed or stale cell does not count.
law missing_cell_does_not_count:
  {M.counts(M.CNone{}) == False{} : Bool}

law failed_cell_does_not_count:
  {M.counts(M.CFail{}) == False{} : Bool}

# R2: CPassOtherSha counts as CNone, at every position of every matrix.
law other_sha_does_not_count:
  {M.counts(M.CPassOtherSha{}) == M.counts(M.CNone{}) : Bool}

law other_sha_is_missing:
  for +pre: M.Cells
  for +r: M.Req
  for +post: M.Cells
  for b: M.Blocker
  {M.decide(M.append(pre, M.KCell{r, M.CPassOtherSha{}, post}), b) == M.decide(M.append(pre, M.KCell{r, M.CNone{}, post}), b) : M.Status}

# R2: a stale pass merged with other receipts of the same cell adds nothing.
law stale_pass_adds_nothing_left:
  for c: M.Cell
  {M.counts(M.merge_cell(M.CPassOtherSha{}, c)) == M.counts(c) : Bool}

law stale_pass_adds_nothing_right:
  for c: M.Cell
  {M.counts(M.merge_cell(c, M.CPassOtherSha{})) == M.counts(c) : Bool}

law missing_adds_nothing:
  for c: M.Cell
  {M.merge_cell(M.CNone{}, c) == c : M.Cell}

# A failed run on the candidate pair is never hidden by a pass of the same cell.
law candidate_fail_wins_left:
  for c: M.Cell
  {M.merge_cell(M.CFail{}, c) == M.CFail{} : M.Cell}

law candidate_fail_wins_right:
  for c: M.Cell
  {M.merge_cell(c, M.CFail{}) == M.CFail{} : M.Cell}

# R3: a blocker can give SBlocked*, never SReady. BNoReason is not a blocker.
law owner_blocker_blocks:
  for cs: M.Cells
  {M.decide(cs, M.BOwner{}) == M.SBlockedOwner{} : M.Status}

law external_blocker_blocks:
  for cs: M.Cells
  {M.decide(cs, M.BExternal{}) == M.SBlockedExternal{} : M.Status}

law no_reason_is_not_ready:
  for cs: M.Cells
  {M.decide(cs, M.BNoReason{}) == M.SNotReady{} : M.Status}

law owner_blocker_dominates_left:
  for b: M.Blocker
  {M.merge_blocker(M.BOwner{}, b) == M.BOwner{} : M.Blocker}

law owner_blocker_dominates_right:
  for a: M.Blocker
  {M.merge_blocker(a, M.BOwner{}) == M.BOwner{} : M.Blocker}

law no_blocker_is_identity:
  for b: M.Blocker
  {M.merge_blocker(M.BNone{}, b) == b : M.Blocker}

# Without a blocker, READY is exactly "every cell counts and the shape is REQUIRED".
law ready_iff_complete:
  for cs: M.Cells
  {M.is_ready(M.decide(cs, M.BNone{})) == M.complete(cs) : Bool}

# R4: REQUIRED is the constant in MODEL (32 cells). A matrix that misses a required
# cell, holds an extra one, or holds them in another order is never ready.
law required_count_is_32:
  {M.required_count() == 32n : Nat}

law wrong_shape_never_ready:
  for cs: M.Cells
  for b: M.Blocker
  for h: {M.shape_ok(cs, 0n) == False{} : Bool}
  {M.is_ready(M.decide(cs, b)) == False{} : Bool}

# Non-vacuity: the full REQUIRED matrix on the candidate pair is READY, and the same
# matrix on another pair is not.
law full_candidate_matrix_ready:
  {M.decide(M.required_all(M.CPassCandidate{}), M.BNone{}) == M.SReady{} : M.Status}

law full_other_sha_matrix_not_ready:
  {M.decide(M.required_all(M.CPassOtherSha{}), M.BNone{}) == M.SNotReady{} : M.Status}

# R5: a receipt counts only when both of its shas are the candidate pair.
law z0_sha_mismatch_never_counts:
  for o: M.Outcome
  for i: Bool
  {M.counts(M.classify(o, False{}, i)) == False{} : Bool}

law z0int_sha_mismatch_never_counts:
  for o: M.Outcome
  for z: Bool
  {M.counts(M.classify(o, z, False{})) == False{} : Bool}

law missing_receipt_is_none:
  for z: Bool
  for i: Bool
  {M.classify(M.OMissing{}, z, i) == M.CNone{} : M.Cell}

law candidate_pass_counts:
  {M.classify(M.OPass{}, True{}, True{}) == M.CPassCandidate{} : M.Cell}
