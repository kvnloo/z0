# z0 onboard kernel: may the onboarder apply one step, or must it ask or refuse?
# The operational twin is lib/z0/onboard/kernel.py, the ONLY code that decides
# refuse/ask/allow (design §11). Each decide_* below is a small finite function;
# tests/onboard/test_kernel_twin.py runs every row of every domain through both.
# Observation of the inputs (host.json facts, grants, sources) is not proven here.
import Base

type Mode is Data:
  MAuto{}
  MGuided{}

type ConsentClass is Data:
  C0{}
  C1{}
  C2{}

# Who granted: a per-step TTY yes, a flag (--yes/--accept), or an LLM answer.
type Source is Data:
  SrcTty{}
  SrcFlag{}
  SrcLlm{}

# host_id of a recorded host.json/answers/receipt versus the current detection.
type HostMatch is Data:
  HFresh{}
  HSame{}
  HOther{}

type BindClass is Data:
  BLoopback{}
  BTailnet{}
  BWildcard{}
  BLan{}

# Where a tailnet IPv4 came from: this detection, a recorded/other host, or nowhere.
type IpSource is Data:
  IpCurrent{}
  IpStale{}
  IpNone{}

type RootKind is Data:
  RkRelease{}
  RkOwnedVenv{}
  RkToolchain{}
  RkCheckout{}
  RkBuildTree{}
  RkOther{}

type Provider is Data:
  PvLocal{}
  PvClaude{}
  PvCodex{}
  PvOpenRouterFree{}
  PvVercelFree{}
  PvGrok{}
  PvCursor{}
  PvUnlisted{}

# Which gate family applies to a component.
type Gate is Data:
  GGeneric{}
  GDash{}
  GZ0int{}

type Flavour is Data:
  FCurrent{}
  FLegacy{}

# Evidence that a pinned rev is on origin: proven, disproven, or not checked
# (no origin mirror and no checkout that holds it).
type RevOrigin is Data:
  OriginYes{}
  OriginNo{}
  OriginUnknown{}

type Maturity is Data:
  MtStable{}
  MtShadow{}
  MtIdea{}

type HwClass is Data:
  HwNvidia{}
  HwAmd{}
  HwApple{}
  HwIntelMac{}
  HwCpu{}

# A python in [3.10, 3.14): already present, can be made (uv), or impossible.
type PyWindow is Data:
  PyPresent{}
  PyMakeable{}
  PyImpossible{}

type RamTier is Data:
  RamLt4{}
  Ram4to8{}
  Ram8to16{}
  RamGt16{}

type DiskTier is Data:
  DiskLt3{}
  Disk3to10{}
  Disk10to40{}
  DiskGt40{}

type Reason is Data:
  RHostMismatch{}
  RC2NeverAuto{}
  RC2Confirm{}
  RC1Ungranted{}
  ROpenBind{}
  RStaleIp{}
  RNoTailnet{}
  RThroughCheckout{}
  ROutsideRoots{}
  RForbiddenProvider{}
  RUnlistedProvider{}
  RQuota{}
  RIdea{}
  RRevNotOnOrigin{}
  RLegacyFlavour{}
  RIntelMac{}
  RPythonWindow{}
  RRamLow{}
  RShadow{}
  RRevUnverified{}
  RAdoptedOtherSha{}

type Verdict is Data:
  VAllow{}
  VAsk{reason: Reason}
  VUnavailable{reason: Reason}
  VRefuse{reason: Reason}

type Profile is Data:
  PfPersonal{}
  PfCore{}
  PfRefuse{}

type TorchIndex is Data:
  IxCpu{}
  IxPypi{}
  IxRocm{}
  IxNone{}

type Replan is Data:
  RpProceed{}
  RpShowDiff{}
  RpReconfirm{}

# H1: never fall back to another host's record.
def decide_host(h: HostMatch) -> Verdict:
  match h:
    case HFresh{}:
      VAllow{}
    case HSame{}:
      VAllow{}
    case HOther{}:
      VRefuse{RHostMismatch{}}

def granted_or(granted: Bool, reason: Reason) -> Verdict:
  match granted:
    case True{}:
      VAllow{}
    case False{}:
      VAsk{reason}

# C2/L-LLM: a C1 step needs a grant, and an LLM answer is never a grant.
def consent_c1(granted: Bool, source: Source) -> Verdict:
  match source:
    case SrcTty{}:
      granted_or(granted, RC1Ungranted{})
    case SrcFlag{}:
      granted_or(granted, RC1Ungranted{})
    case SrcLlm{}:
      VAsk{RC1Ungranted{}}

# C1: auto never applies C2; guided applies it only on a per-step TTY yes.
def consent_c2(mode: Mode, granted: Bool, source: Source) -> Verdict:
  match mode:
    case MAuto{}:
      VAsk{RC2NeverAuto{}}
    case MGuided{}:
      match source:
        case SrcTty{}:
          granted_or(granted, RC2Confirm{})
        case SrcFlag{}:
          VAsk{RC2Confirm{}}
        case SrcLlm{}:
          VAsk{RC2Confirm{}}

def decide_consent(mode: Mode, cls: ConsentClass, granted: Bool, source: Source) -> Verdict:
  match cls:
    case C0{}:
      VAllow{}
    case C1{}:
      consent_c1(granted, source)
    case C2{}:
      consent_c2(mode, granted, source)

# S2/H2: binds are loopback or this detection's tailnet IPv4; nothing else.
def decide_bind(bind: BindClass, ip: IpSource) -> Verdict:
  match bind:
    case BLoopback{}:
      VAllow{}
    case BTailnet{}:
      match ip:
        case IpCurrent{}:
          VAllow{}
        case IpStale{}:
          VRefuse{RStaleIp{}}
        case IpNone{}:
          VUnavailable{RNoTailnet{}}
    case BWildcard{}:
      VRefuse{ROpenBind{}}
    case BLan{}:
      VRefuse{ROpenBind{}}

# S1: live code runs only from releases, owned venvs or owned toolchains.
def decide_exec_root(root: RootKind) -> Verdict:
  match root:
    case RkRelease{}:
      VAllow{}
    case RkOwnedVenv{}:
      VAllow{}
    case RkToolchain{}:
      VAllow{}
    case RkCheckout{}:
      VRefuse{RThroughCheckout{}}
    case RkBuildTree{}:
      VRefuse{RThroughCheckout{}}
    case RkOther{}:
      VRefuse{ROutsideRoots{}}

# S3: an existing unit is adopted, never duplicated. Same SHA: kept. Another SHA:
# redeploying it is C2, so ask (decide_consent then decides that C2 step).
def adopt_sha(same_sha: Bool) -> Verdict:
  match same_sha:
    case True{}:
      VAllow{}
    case False{}:
      VAsk{RAdoptedOtherSha{}}

def decide_adopt(unit_exists: Bool, same_sha: Bool) -> Verdict:
  match unit_exists:
    case False{}:
      VAllow{}
    case True{}:
      adopt_sha(same_sha)

# P1: grok and cursor are refused in every role; remote providers need consent.
def decide_provider(p: Provider) -> Verdict:
  match p:
    case PvLocal{}:
      VAllow{}
    case PvClaude{}:
      VAsk{RQuota{}}
    case PvCodex{}:
      VAsk{RQuota{}}
    case PvOpenRouterFree{}:
      VAsk{RQuota{}}
    case PvVercelFree{}:
      VAsk{RQuota{}}
    case PvGrok{}:
      VRefuse{RForbiddenProvider{}}
    case PvCursor{}:
      VRefuse{RForbiddenProvider{}}
    case PvUnlisted{}:
      VRefuse{RUnlistedProvider{}}

def z0int_ram(ram: RamTier) -> Verdict:
  match ram:
    case RamLt4{}:
      VUnavailable{RRamLow{}}
    case Ram4to8{}:
      VUnavailable{RRamLow{}}
    case Ram8to16{}:
      VAllow{}
    case RamGt16{}:
      VAllow{}

def z0int_py(py: PyWindow, ram: RamTier) -> Verdict:
  match py:
    case PyPresent{}:
      z0int_ram(ram)
    case PyMakeable{}:
      z0int_ram(ram)
    case PyImpossible{}:
      VRefuse{RPythonWindow{}}

# Z1: intel_mac has no torch 2.10 wheel; python must fit [3.10, 3.14).
def z0int_hw(hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
  match hw:
    case HwNvidia{}:
      z0int_py(py, ram)
    case HwAmd{}:
      z0int_py(py, ram)
    case HwApple{}:
      z0int_py(py, ram)
    case HwIntelMac{}:
      VRefuse{RIntelMac{}}
    case HwCpu{}:
      z0int_py(py, ram)

# D2: a legacy dash checkout (0.0.0.0 bind, Expo Go) is never deployed.
def dash_flavour(flavour: Flavour) -> Verdict:
  match flavour:
    case FCurrent{}:
      VAllow{}
    case FLegacy{}:
      VRefuse{RLegacyFlavour{}}

def component_gate(gate: Gate, flavour: Flavour, hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
  match gate:
    case GGeneric{}:
      VAllow{}
    case GDash{}:
      dash_flavour(flavour)
    case GZ0int{}:
      z0int_hw(hw, py, ram)

# D1: a dash rev that could not be checked on origin is unavailable with its own
# reason (not "maintainer must push"); other gates proceed and the plan warns.
def unverified_rev(gate: Gate, flavour: Flavour, hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
  match gate:
    case GGeneric{}:
      VAllow{}
    case GDash{}:
      VUnavailable{RRevUnverified{}}
    case GZ0int{}:
      z0int_hw(hw, py, ram)

# D1/public-ready: a pinned rev missing from origin makes the component unavailable.
def component_gates(gate: Gate, rev: RevOrigin, flavour: Flavour, hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
  match rev:
    case OriginNo{}:
      VUnavailable{RRevNotOnOrigin{}}
    case OriginYes{}:
      component_gate(gate, flavour, hw, py, ram)
    case OriginUnknown{}:
      unverified_rev(gate, flavour, hw, py, ram)

# M2: a shadow component that passes every gate is still only asked (C2).
def shadow_of(v: Verdict) -> Verdict:
  match v:
    case VAllow{}:
      VAsk{RShadow{}}
    case VAsk{reason}:
      VAsk{reason}
    case VUnavailable{reason}:
      VUnavailable{reason}
    case VRefuse{reason}:
      VRefuse{reason}

# M1: an idea (memento) is never planned.
def decide_component(gate: Gate, rev: RevOrigin, flavour: Flavour, maturity: Maturity, hw: HwClass, py: PyWindow, ram: RamTier) -> Verdict:
  match maturity:
    case MtStable{}:
      component_gates(gate, rev, flavour, hw, py, ram)
    case MtShadow{}:
      shadow_of(component_gates(gate, rev, flavour, hw, py, ram))
    case MtIdea{}:
      VRefuse{RIdea{}}

def profile_py(py: PyWindow) -> Profile:
  match py:
    case PyPresent{}:
      PfPersonal{}
    case PyMakeable{}:
      PfPersonal{}
    case PyImpossible{}:
      PfCore{}

def profile_hw(hw: HwClass, py: PyWindow) -> Profile:
  match hw:
    case HwNvidia{}:
      profile_py(py)
    case HwAmd{}:
      profile_py(py)
    case HwApple{}:
      profile_py(py)
    case HwIntelMac{}:
      PfCore{}
    case HwCpu{}:
      profile_py(py)

def profile_ram(ram: RamTier, hw: HwClass, py: PyWindow) -> Profile:
  match ram:
    case RamLt4{}:
      PfCore{}
    case Ram4to8{}:
      PfCore{}
    case Ram8to16{}:
      profile_hw(hw, py)
    case RamGt16{}:
      profile_hw(hw, py)

# §5.2 auto default profile: personal, else core when disk >= 3, else refuse.
def decide_profile(ram: RamTier, disk: DiskTier, hw: HwClass, py: PyWindow) -> Profile:
  match disk:
    case DiskLt3{}:
      PfRefuse{}
    case Disk3to10{}:
      PfCore{}
    case Disk10to40{}:
      profile_ram(ram, hw, py)
    case DiskGt40{}:
      profile_ram(ram, hw, py)

def torch_gpu(ok: Bool, index: TorchIndex) -> TorchIndex:
  match ok:
    case True{}:
      index
    case False{}:
      IxCpu{}

def torch_disk(disk_low: Bool, gpu: TorchIndex) -> TorchIndex:
  match disk_low:
    case True{}:
      IxCpu{}
    case False{}:
      gpu

# Z2: torch==2.10.0 index; cpu class or disk < 10 GiB takes the cpu index.
def decide_torch_index(hw: HwClass, cuda_ok: Bool, rocm: Bool, disk_low: Bool) -> TorchIndex:
  match hw:
    case HwNvidia{}:
      torch_disk(disk_low, torch_gpu(cuda_ok, IxPypi{}))
    case HwAmd{}:
      torch_disk(disk_low, torch_gpu(rocm, IxRocm{}))
    case HwApple{}:
      torch_disk(disk_low, IxPypi{})
    case HwIntelMac{}:
      IxNone{}
    case HwCpu{}:
      IxCpu{}

# C2: a freshness re-plan that widens grants re-confirms; --yes cannot widen.
def decide_replan(drift: Bool, widens: Bool, yes: Bool) -> Replan:
  match drift:
    case False{}:
      RpProceed{}
    case True{}:
      match widens:
        case True{}:
          RpReconfirm{}
        case False{}:
          RpShowDiff{}

def is_allow(v: Verdict) -> Bool:
  match v:
    case VAllow{}:
      True{}
    case VAsk{reason}:
      False{}
    case VUnavailable{reason}:
      False{}
    case VRefuse{reason}:
      False{}

def is_refuse(v: Verdict) -> Bool:
  match v:
    case VAllow{}:
      False{}
    case VAsk{reason}:
      False{}
    case VUnavailable{reason}:
      False{}
    case VRefuse{reason}:
      True{}

# Exhaustive Python/Bend parity uses these lossless codes: kind * 100 + reason.
def reason_code(r: Reason) -> Nat:
  match r:
    case RHostMismatch{}:
      1n
    case RC2NeverAuto{}:
      2n
    case RC2Confirm{}:
      3n
    case RC1Ungranted{}:
      4n
    case ROpenBind{}:
      5n
    case RStaleIp{}:
      6n
    case RNoTailnet{}:
      7n
    case RThroughCheckout{}:
      8n
    case ROutsideRoots{}:
      9n
    case RForbiddenProvider{}:
      10n
    case RUnlistedProvider{}:
      11n
    case RQuota{}:
      12n
    case RIdea{}:
      13n
    case RRevNotOnOrigin{}:
      14n
    case RLegacyFlavour{}:
      15n
    case RIntelMac{}:
      16n
    case RPythonWindow{}:
      17n
    case RRamLow{}:
      18n
    case RShadow{}:
      19n
    case RRevUnverified{}:
      20n
    case RAdoptedOtherSha{}:
      21n

def code_verdict(v: Verdict) -> Nat:
  match v:
    case VAllow{}:
      0n
    case VAsk{reason}:
      (100n + reason_code(reason) : Nat)
    case VUnavailable{reason}:
      (200n + reason_code(reason) : Nat)
    case VRefuse{reason}:
      (300n + reason_code(reason) : Nat)

def code_profile(p: Profile) -> Nat:
  match p:
    case PfPersonal{}:
      0n
    case PfCore{}:
      1n
    case PfRefuse{}:
      2n

def code_index(i: TorchIndex) -> Nat:
  match i:
    case IxCpu{}:
      0n
    case IxPypi{}:
      1n
    case IxRocm{}:
      2n
    case IxNone{}:
      3n

def code_replan(r: Replan) -> Nat:
  match r:
    case RpProceed{}:
      0n
    case RpShowDiff{}:
      1n
    case RpReconfirm{}:
      2n
