# contrib_ready: may the "ready to send" message go out for one candidate commit pair
# (z0_sha, z0int_sha)? Contributor spec §4.4. The operational twin is
# scripts/contrib_ready.py (decide_ready, may_announce); tests/contrib_ready/ runs
# every row of every finite domain below through both, plus bounded matrices.
# Reading receipts, comparing shas and running the cells are not proven here: the
# twin turns each receipt into an Outcome and two pair-match booleans.
import Base

# One required cell after its receipts are read. Only CPassCandidate counts (R2).
type Cell is Data:
  CNone{}
  CFail{}
  CPassOtherSha{}
  CPassCandidate{}

# What blocks the announcement. BNoReason is a blocker record without a reason: it
# is not a blocker and gives SNotReady (R3).
type Blocker is Data:
  BNone{}
  BNoReason{}
  BOwner{}
  BExternal{}

type Status is Data:
  SNotReady{}
  SReady{}
  SBlockedOwner{}
  SBlockedExternal{}

# What one receipt file says about its cell.
type Outcome is Data:
  OMissing{}
  OFail{}
  OPass{}

# R4: the REQUIRED set is this constant. Agent cells are
# {claude,codex} x {frontend,ml-research,systems-rust} x {run1..3}, then the
# deterministic and container cells. A change here changes the MODEL hash, and the
# `contrib-ready` CI job then needs an owner-approved commit (CODEOWNERS).
type Req is Data:
  QClaudeFrontendRun1{}
  QClaudeFrontendRun2{}
  QClaudeFrontendRun3{}
  QClaudeMlResearchRun1{}
  QClaudeMlResearchRun2{}
  QClaudeMlResearchRun3{}
  QClaudeSystemsRustRun1{}
  QClaudeSystemsRustRun2{}
  QClaudeSystemsRustRun3{}
  QCodexFrontendRun1{}
  QCodexFrontendRun2{}
  QCodexFrontendRun3{}
  QCodexMlResearchRun1{}
  QCodexMlResearchRun2{}
  QCodexMlResearchRun3{}
  QCodexSystemsRustRun1{}
  QCodexSystemsRustRun2{}
  QCodexSystemsRustRun3{}
  QOnboardContainer{}
  QSmoke{}
  QE1{}
  QE2{}
  QG1{}
  QG2{}
  QG3{}
  QG4{}
  QG5{}
  QP1{}
  QP2{}
  QC1{}
  QW1{}
  QLawsCi{}

# The matrix: one (req, cell) entry per required cell, in REQUIRED order.
type Cells is Data:
  KEnd{}
  KCell{req: Req, cell: Cell, rest: Cells}

def required_count() -> Nat:
  32n

def req_code(r: Req) -> Nat:
  match r:
    case QClaudeFrontendRun1{}:
      0n
    case QClaudeFrontendRun2{}:
      1n
    case QClaudeFrontendRun3{}:
      2n
    case QClaudeMlResearchRun1{}:
      3n
    case QClaudeMlResearchRun2{}:
      4n
    case QClaudeMlResearchRun3{}:
      5n
    case QClaudeSystemsRustRun1{}:
      6n
    case QClaudeSystemsRustRun2{}:
      7n
    case QClaudeSystemsRustRun3{}:
      8n
    case QCodexFrontendRun1{}:
      9n
    case QCodexFrontendRun2{}:
      10n
    case QCodexFrontendRun3{}:
      11n
    case QCodexMlResearchRun1{}:
      12n
    case QCodexMlResearchRun2{}:
      13n
    case QCodexMlResearchRun3{}:
      14n
    case QCodexSystemsRustRun1{}:
      15n
    case QCodexSystemsRustRun2{}:
      16n
    case QCodexSystemsRustRun3{}:
      17n
    case QOnboardContainer{}:
      18n
    case QSmoke{}:
      19n
    case QE1{}:
      20n
    case QE2{}:
      21n
    case QG1{}:
      22n
    case QG2{}:
      23n
    case QG3{}:
      24n
    case QG4{}:
      25n
    case QG5{}:
      26n
    case QP1{}:
      27n
    case QP2{}:
      28n
    case QC1{}:
      29n
    case QW1{}:
      30n
    case QLawsCi{}:
      31n

# R2: only a pass on the candidate pair counts. A pass on another pair is no pass.
def counts(c: Cell) -> Bool:
  match c:
    case CNone{}:
      False{}
    case CFail{}:
      False{}
    case CPassOtherSha{}:
      False{}
    case CPassCandidate{}:
      True{}

def pass_on(z0_same: Bool, z0int_same: Bool) -> Cell:
  match z0_same:
    case True{}:
      match z0int_same:
        case True{}:
          CPassCandidate{}
        case False{}:
          CPassOtherSha{}
    case False{}:
      CPassOtherSha{}

def fail_on(z0_same: Bool, z0int_same: Bool) -> Cell:
  match z0_same:
    case True{}:
      match z0int_same:
        case True{}:
          CFail{}
        case False{}:
          CNone{}
    case False{}:
      CNone{}

# R5: a receipt counts only when BOTH of its shas equal the candidate pair. A stale
# fail does not block a fresh pass, and a stale pass never counts.
def classify(o: Outcome, z0_same: Bool, z0int_same: Bool) -> Cell:
  match o:
    case OMissing{}:
      CNone{}
    case OFail{}:
      fail_on(z0_same, z0int_same)
    case OPass{}:
      pass_on(z0_same, z0int_same)

# Several receipts for one cell: a candidate fail wins, then a candidate pass.
def merge_none(b: Cell) -> Cell:
  b

def merge_other(b: Cell) -> Cell:
  match b:
    case CNone{}:
      CPassOtherSha{}
    case CFail{}:
      CFail{}
    case CPassOtherSha{}:
      CPassOtherSha{}
    case CPassCandidate{}:
      CPassCandidate{}

def merge_candidate(b: Cell) -> Cell:
  match b:
    case CNone{}:
      CPassCandidate{}
    case CFail{}:
      CFail{}
    case CPassOtherSha{}:
      CPassCandidate{}
    case CPassCandidate{}:
      CPassCandidate{}

def merge_cell(a: Cell, b: Cell) -> Cell:
  match a:
    case CNone{}:
      merge_none(b)
    case CFail{}:
      CFail{}
    case CPassOtherSha{}:
      merge_other(b)
    case CPassCandidate{}:
      merge_candidate(b)

# Several blocker records: owner, then external, then a reasonless record.
def merge_blocker(a: Blocker, b: Blocker) -> Blocker:
  match a:
    case BOwner{}:
      BOwner{}
    case BExternal{}:
      match b:
        case BOwner{}:
          BOwner{}
        case BExternal{}:
          BExternal{}
        case BNoReason{}:
          BExternal{}
        case BNone{}:
          BExternal{}
    case BNoReason{}:
      match b:
        case BOwner{}:
          BOwner{}
        case BExternal{}:
          BExternal{}
        case BNoReason{}:
          BNoReason{}
        case BNone{}:
          BNoReason{}
    case BNone{}:
      b

# R1/R2: every entry counts.
def all_count(cs: Cells) -> Bool:
  match cs:
    case KEnd{}:
      True{}
    case KCell{r, c, rest}:
      Bool.and(counts(c), all_count(rest))

# R4: the entries are exactly REQUIRED, in order: nothing missing, extra or swapped.
def shape_ok(cs: Cells, +i: Nat) -> Bool:
  match cs:
    case KEnd{}:
      Nat.is_eq(i, required_count())
    case KCell{r, c, rest}:
      Bool.and(Nat.is_eq(req_code(r), i), shape_ok(rest, 1n+i))

def complete(+cs: Cells) -> Bool:
  Bool.and(all_count(cs), shape_ok(cs, 0n))

def ready_if(ok: Bool) -> Status:
  match ok:
    case True{}:
      SReady{}
    case False{}:
      SNotReady{}

# R3: a blocker can give SBlocked*, never SReady; BNoReason gives SNotReady.
def decide_with(b: Blocker, ok: Bool) -> Status:
  match b:
    case BNone{}:
      ready_if(ok)
    case BNoReason{}:
      SNotReady{}
    case BOwner{}:
      SBlockedOwner{}
    case BExternal{}:
      SBlockedExternal{}

def decide(cs: Cells, b: Blocker) -> Status:
  decide_with(b, complete(cs))

def is_ready(s: Status) -> Bool:
  match s:
    case SNotReady{}:
      False{}
    case SReady{}:
      True{}
    case SBlockedOwner{}:
      False{}
    case SBlockedExternal{}:
      False{}

def append(xs: Cells, ys: Cells) -> Cells:
  match xs:
    case KEnd{}:
      ys
    case KCell{r, c, rest}:
      KCell{r, c, append(rest, ys)}

# The REQUIRED matrix with every cell set to c (non-vacuity of the laws).
def required_all(+c: Cell) -> Cells:
  KCell{QClaudeFrontendRun1{}, c, KCell{QClaudeFrontendRun2{}, c, KCell{QClaudeFrontendRun3{}, c,
  KCell{QClaudeMlResearchRun1{}, c, KCell{QClaudeMlResearchRun2{}, c, KCell{QClaudeMlResearchRun3{}, c,
  KCell{QClaudeSystemsRustRun1{}, c, KCell{QClaudeSystemsRustRun2{}, c, KCell{QClaudeSystemsRustRun3{}, c,
  KCell{QCodexFrontendRun1{}, c, KCell{QCodexFrontendRun2{}, c, KCell{QCodexFrontendRun3{}, c,
  KCell{QCodexMlResearchRun1{}, c, KCell{QCodexMlResearchRun2{}, c, KCell{QCodexMlResearchRun3{}, c,
  KCell{QCodexSystemsRustRun1{}, c, KCell{QCodexSystemsRustRun2{}, c, KCell{QCodexSystemsRustRun3{}, c,
  KCell{QOnboardContainer{}, c, KCell{QSmoke{}, c, KCell{QE1{}, c, KCell{QE2{}, c,
  KCell{QG1{}, c, KCell{QG2{}, c, KCell{QG3{}, c, KCell{QG4{}, c, KCell{QG5{}, c,
  KCell{QP1{}, c, KCell{QP2{}, c, KCell{QC1{}, c, KCell{QW1{}, c, KCell{QLawsCi{}, c,
  KEnd{}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}

# Exhaustive Python/Bend parity uses these lossless codes.
def code_cell(c: Cell) -> Nat:
  match c:
    case CNone{}:
      0n
    case CFail{}:
      1n
    case CPassOtherSha{}:
      2n
    case CPassCandidate{}:
      3n

def code_blocker(b: Blocker) -> Nat:
  match b:
    case BNone{}:
      0n
    case BNoReason{}:
      1n
    case BOwner{}:
      2n
    case BExternal{}:
      3n

def code_status(s: Status) -> Nat:
  match s:
    case SNotReady{}:
      0n
    case SReady{}:
      1n
    case SBlockedOwner{}:
      2n
    case SBlockedExternal{}:
      3n

def code_bool(b: Bool) -> Nat:
  match b:
    case False{}:
      0n
    case True{}:
      1n
