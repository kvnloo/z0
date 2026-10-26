# All proofs implement the exact, owner-reviewed LAWS.bend signatures.
# Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def Laws.other_host_refuses():
  {==}

def Laws.same_host_allows():
  {==}

def Laws.fresh_host_allows():
  {==}

def Laws.c0_applies(m, g, s):
  {==}

def Laws.auto_never_c2(g, s):
  {==}

def Laws.c1_needs_grant(m, s):
  match s:
    case M.SrcTty{}:
      {==}
    case M.SrcFlag{}:
      {==}
    case M.SrcLlm{}:
      {==}

def Laws.flag_never_grants_c2(m, g):
  match m:
    case M.MAuto{}:
      {==}
    case M.MGuided{}:
      {==}

def Laws.replan_cannot_widen(y):
  {==}

def Laws.replan_within_grants_shows_diff(y):
  {==}

def llm_c2(m: M.Mode, g: Bool) -> {M.consent_c2(m, g, M.SrcLlm{}) == M.consent_c2(m, False{}, M.SrcTty{}) : M.Verdict}:
  match m:
    case M.MAuto{}:
      {==}
    case M.MGuided{}:
      {==}

def Laws.llm_no_escalation(m, c, g):
  match c:
    case M.C0{}:
      {==}
    case M.C1{}:
      {==}
    case M.C2{}:
      llm_c2(m, g)

def Laws.wildcard_bind_refuses(ip):
  {==}

def Laws.lan_bind_refuses(ip):
  {==}

def Laws.loopback_bind_allows(ip):
  {==}

def Laws.stale_tailnet_ip_refuses():
  {==}

def Laws.no_tailnet_is_unavailable():
  {==}

def Laws.checkout_root_refuses():
  {==}

def Laws.build_tree_root_refuses():
  {==}

def Laws.undeclared_root_refuses():
  {==}

def Laws.grok_refused():
  {==}

def Laws.cursor_refused():
  {==}

def Laws.unlisted_provider_refused():
  {==}

def Laws.remote_provider_needs_consent():
  {==}

def Laws.idea_never_planned(g, r, f, h, p, ra):
  {==}

# Whatever the gates answer, shadow_of never turns it into VAllow.
def shadow_never_allow(v: M.Verdict) -> {M.is_allow(M.shadow_of(v)) == False{} : Bool}:
  match v:
    case M.VAllow{}:
      {==}
    case M.VAsk{reason}:
      {==}
    case M.VUnavailable{reason}:
      {==}
    case M.VRefuse{reason}:
      {==}

def Laws.shadow_never_allowed(g, r, f, h, p, ra):
  shadow_never_allow(M.component_gates(g, r, f, h, p, ra))

def Laws.rev_not_on_origin_unavailable(g, f, h, p, ra):
  {==}

def Laws.legacy_dash_refused(h, p, ra):
  {==}

def Laws.z0int_intel_mac_refused(f, p, ra):
  {==}

def Laws.z0int_python_window_refused(f, h, ra):
  match h:
    case M.HwNvidia{}:
      {==}
    case M.HwAmd{}:
      {==}
    case M.HwApple{}:
      {==}
    case M.HwIntelMac{}:
      {==}
    case M.HwCpu{}:
      {==}

# Below 8 GiB the z0int python gate answers refuse or unavailable, never allow.
def low_ram_py(p: M.PyWindow, ra: M.RamTier, low: {M.is_allow(M.z0int_ram(ra)) == False{} : Bool}) -> {M.is_allow(M.z0int_py(p, ra)) == False{} : Bool}:
  match p:
    case M.PyPresent{}:
      low
    case M.PyMakeable{}:
      low
    case M.PyImpossible{}:
      {==}

def low_ram_hw(h: M.HwClass, p: M.PyWindow, ra: M.RamTier, low: {M.is_allow(M.z0int_ram(ra)) == False{} : Bool}) -> {M.is_allow(M.z0int_hw(h, p, ra)) == False{} : Bool}:
  match h:
    case M.HwNvidia{}:
      low_ram_py(p, ra, low)
    case M.HwAmd{}:
      low_ram_py(p, ra, low)
    case M.HwApple{}:
      low_ram_py(p, ra, low)
    case M.HwIntelMac{}:
      {==}
    case M.HwCpu{}:
      low_ram_py(p, ra, low)

def Laws.z0int_ram_lt4_not_allowed(f, h, p):
  low_ram_hw(h, p, M.RamLt4{}, {==})

def Laws.z0int_ram_4to8_not_allowed(f, h, p):
  low_ram_hw(h, p, M.Ram4to8{}, {==})

def Laws.cpu_class_cpu_index(c, r, d):
  {==}

def Laws.low_disk_cpu_index_nvidia(c, r):
  {==}

def Laws.intel_mac_no_torch(c, r, d):
  {==}

def Laws.tiny_disk_refuses_profile(r, h, p):
  {==}

def Laws.intel_mac_profile_core(r, p):
  match r:
    case M.RamLt4{}:
      {==}
    case M.Ram4to8{}:
      {==}
    case M.Ram8to16{}:
      {==}
    case M.RamGt16{}:
      {==}
