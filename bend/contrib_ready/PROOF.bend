# All proofs implement the exact, owner-reviewed LAWS.bend signatures.
# Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def and_false(x: Bool) -> {Bool.and(x, False{}) == False{} : Bool}:
  match x:
    case False{}:
      {==}
    case True{}:
      {==}

def not_ready_false(b: M.Blocker) -> {M.is_ready(M.decide_with(b, False{})) == False{} : Bool}:
  match b:
    case M.BNone{}:
      {==}
    case M.BNoReason{}:
      {==}
    case M.BOwner{}:
      {==}
    case M.BExternal{}:
      {==}

# A cell that does not count makes the whole matrix fail all_count (induction on pre).
def uncounted_all(pre: M.Cells, r: M.Req, c: M.Cell, post: M.Cells, h: {M.counts(c) == False{} : Bool}) -> {M.all_count(M.append(pre, M.KCell{r, c, post})) == False{} : Bool}:
  match pre:
    case M.KEnd{}:
      %Equal.sym(Bool, M.counts(c), False{}, h) : {Bool.and(_, M.all_count(post)) == False{} : Bool}
      {==}
    case M.KCell{r2, c2, rest}:
      %Equal.sym(Bool, M.all_count(M.append(rest, M.KCell{r, c, post})), False{}, uncounted_all(rest, r, c, post, h)) : {Bool.and(M.counts(c2), _) == False{} : Bool}
      and_false(M.counts(c2))

def Laws.uncounted_cell_never_ready(pre, r, c, post, b, h):
  %Equal.sym(Bool, M.all_count(M.append(pre, M.KCell{r, c, post})), False{}, uncounted_all(pre, r, c, post, h)) : {M.is_ready(M.decide_with(b, Bool.and(_, M.shape_ok(M.append(pre, M.KCell{r, c, post}), 0n)))) == False{} : Bool}
  not_ready_false(b)

def Laws.missing_cell_does_not_count():
  {==}

def Laws.failed_cell_does_not_count():
  {==}

def Laws.other_sha_does_not_count():
  {==}

def Laws.other_sha_is_missing(pre, r, post, b):
  %Equal.sym(Bool, M.all_count(M.append(pre, M.KCell{r, M.CPassOtherSha{}, post})), False{}, uncounted_all(pre, r, M.CPassOtherSha{}, post, {==})) : {M.decide_with(b, Bool.and(_, M.shape_ok(M.append(pre, M.KCell{r, M.CPassOtherSha{}, post}), 0n))) == M.decide(M.append(pre, M.KCell{r, M.CNone{}, post}), b) : M.Status}
  %Equal.sym(Bool, M.all_count(M.append(pre, M.KCell{r, M.CNone{}, post})), False{}, uncounted_all(pre, r, M.CNone{}, post, {==})) : {M.decide_with(b, False{}) == M.decide_with(b, Bool.and(_, M.shape_ok(M.append(pre, M.KCell{r, M.CNone{}, post}), 0n))) : M.Status}
  {==}

def Laws.stale_pass_adds_nothing_left(c):
  match c:
    case M.CNone{}:
      {==}
    case M.CFail{}:
      {==}
    case M.CPassOtherSha{}:
      {==}
    case M.CPassCandidate{}:
      {==}

def Laws.stale_pass_adds_nothing_right(c):
  match c:
    case M.CNone{}:
      {==}
    case M.CFail{}:
      {==}
    case M.CPassOtherSha{}:
      {==}
    case M.CPassCandidate{}:
      {==}

def Laws.missing_adds_nothing(c):
  {==}

def Laws.candidate_fail_wins_left(c):
  {==}

def Laws.candidate_fail_wins_right(c):
  match c:
    case M.CNone{}:
      {==}
    case M.CFail{}:
      {==}
    case M.CPassOtherSha{}:
      {==}
    case M.CPassCandidate{}:
      {==}

def Laws.owner_blocker_blocks(cs):
  {==}

def Laws.external_blocker_blocks(cs):
  {==}

def Laws.no_reason_is_not_ready(cs):
  {==}

def Laws.owner_blocker_dominates_left(b):
  {==}

def Laws.owner_blocker_dominates_right(a):
  match a:
    case M.BNone{}:
      {==}
    case M.BNoReason{}:
      {==}
    case M.BOwner{}:
      {==}
    case M.BExternal{}:
      {==}

def Laws.no_blocker_is_identity(b):
  {==}

def ready_if_exact(x: Bool) -> {M.is_ready(M.ready_if(x)) == x : Bool}:
  match x:
    case False{}:
      {==}
    case True{}:
      {==}

def Laws.ready_iff_complete(cs):
  ready_if_exact(M.complete(cs))

def Laws.required_count_is_32():
  {==}

def and_false_not_ready(b: M.Blocker, a: Bool) -> {M.is_ready(M.decide_with(b, Bool.and(a, False{}))) == False{} : Bool}:
  match b:
    case M.BNone{}:
      match a:
        case False{}:
          {==}
        case True{}:
          {==}
    case M.BNoReason{}:
      {==}
    case M.BOwner{}:
      {==}
    case M.BExternal{}:
      {==}

def Laws.wrong_shape_never_ready(cs, b, h):
  %Equal.sym(Bool, M.shape_ok(cs, 0n), False{}, h) : {M.is_ready(M.decide_with(b, Bool.and(M.all_count(cs), _))) == False{} : Bool}
  and_false_not_ready(b, M.all_count(cs))

def Laws.full_candidate_matrix_ready():
  {==}

def Laws.full_other_sha_matrix_not_ready():
  {==}

def Laws.z0_sha_mismatch_never_counts(o, i):
  match o:
    case M.OMissing{}:
      {==}
    case M.OFail{}:
      {==}
    case M.OPass{}:
      {==}

def Laws.z0int_sha_mismatch_never_counts(o, z):
  match o:
    case M.OMissing{}:
      {==}
    case M.OFail{}:
      match z:
        case False{}:
          {==}
        case True{}:
          {==}
    case M.OPass{}:
      match z:
        case False{}:
          {==}
        case True{}:
          {==}

def Laws.missing_receipt_is_none(z, i):
  {==}

def Laws.candidate_pass_counts():
  {==}
