# Owner laws for z0 onboard (design §11), universally quantified over MODEL's domains.
# Each law names the design law it states. Laws I1, R1, X1, H2-artifact-scan, T1, O1
# and P0 rest on tests, not on these proofs. No theorem here verifies the caller's
# observations (host_id, grants, sources, bind facts), permission or host.
import Base
import ./MODEL.bend as M

# H1 host_match: no fallback to another host's record.
law other_host_refuses:
  {M.decide_host(M.HOther{}) == M.VRefuse{M.RHostMismatch{}} : M.Verdict}

law same_host_allows:
  {M.decide_host(M.HSame{}) == M.VAllow{} : M.Verdict}

law fresh_host_allows:
  {M.decide_host(M.HFresh{}) == M.VAllow{} : M.Verdict}

# Consent: C0 is z0-private and always applies.
law c0_applies:
  for m: M.Mode
  for g: Bool
  for s: M.Source
  {M.decide_consent(m, M.C0{}, g, s) == M.VAllow{} : M.Verdict}

# C1 auto_never_c2: auto ∧ C2 → ask, whatever was granted and by whom.
law auto_never_c2:
  for g: Bool
  for s: M.Source
  {M.decide_consent(M.MAuto{}, M.C2{}, g, s) == M.VAsk{M.RC2NeverAuto{}} : M.Verdict}

# C2 grant_bound: a C1 step runs only if its bundle is granted.
law c1_needs_grant:
  for m: M.Mode
  for s: M.Source
  {M.decide_consent(m, M.C1{}, False{}, s) == M.VAsk{M.RC1Ungranted{}} : M.Verdict}

# C2 grant_bound: --yes (a flag) never grants C2, even in guided.
law flag_never_grants_c2:
  for m: M.Mode
  for g: Bool
  {M.is_allow(M.decide_consent(m, M.C2{}, g, M.SrcFlag{})) == False{} : Bool}

# C2 grant_bound: a freshness re-plan that widens grants re-confirms, even under --yes.
law replan_cannot_widen:
  for y: Bool
  {M.decide_replan(True{}, True{}, y) == M.RpReconfirm{} : M.Replan}

law replan_within_grants_shows_diff:
  for y: Bool
  {M.decide_replan(True{}, False{}, y) == M.RpShowDiff{} : M.Replan}

# L-LLM no_escalation: an LLM-sourced answer is never more permissive than no grant.
law llm_no_escalation:
  for m: M.Mode
  for c: M.ConsentClass
  for g: Bool
  {M.decide_consent(m, c, g, M.SrcLlm{}) == M.decide_consent(m, c, False{}, M.SrcTty{}) : M.Verdict}

# S2 closed_bind: only loopback or this detection's tailnet IPv4.
law wildcard_bind_refuses:
  for ip: M.IpSource
  {M.decide_bind(M.BWildcard{}, ip) == M.VRefuse{M.ROpenBind{}} : M.Verdict}

law lan_bind_refuses:
  for ip: M.IpSource
  {M.decide_bind(M.BLan{}, ip) == M.VRefuse{M.ROpenBind{}} : M.Verdict}

law loopback_bind_allows:
  for ip: M.IpSource
  {M.decide_bind(M.BLoopback{}, ip) == M.VAllow{} : M.Verdict}

# H2: tailnet IPs only from the current detection.
law stale_tailnet_ip_refuses:
  {M.decide_bind(M.BTailnet{}, M.IpStale{}) == M.VRefuse{M.RStaleIp{}} : M.Verdict}

law no_tailnet_is_unavailable:
  {M.decide_bind(M.BTailnet{}, M.IpNone{}) == M.VUnavailable{M.RNoTailnet{}} : M.Verdict}

# S1 never_through_checkout: anything with a .git ancestor, or undeclared, refuses.
law checkout_root_refuses:
  {M.decide_exec_root(M.RkCheckout{}) == M.VRefuse{M.RThroughCheckout{}} : M.Verdict}

law build_tree_root_refuses:
  {M.decide_exec_root(M.RkBuildTree{}) == M.VRefuse{M.RThroughCheckout{}} : M.Verdict}

law undeclared_root_refuses:
  {M.decide_exec_root(M.RkOther{}) == M.VRefuse{M.ROutsideRoots{}} : M.Verdict}

# P1 forbidden_provider: grok and cursor are refused in every role.
law grok_refused:
  {M.decide_provider(M.PvGrok{}) == M.VRefuse{M.RForbiddenProvider{}} : M.Verdict}

law cursor_refused:
  {M.decide_provider(M.PvCursor{}) == M.VRefuse{M.RForbiddenProvider{}} : M.Verdict}

law unlisted_provider_refused:
  {M.decide_provider(M.PvUnlisted{}) == M.VRefuse{M.RUnlistedProvider{}} : M.Verdict}

# §7: providers that use the user's account are listed and confirmed, never silent.
law remote_provider_needs_consent:
  {M.decide_provider(M.PvClaude{}) == M.VAsk{M.RQuota{}} : M.Verdict}

# M1: memento-class (idea) components are never planned.
law idea_never_planned:
  for g: M.Gate
  for r: M.RevOrigin
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  for ra: M.RamTier
  {M.decide_component(g, r, f, M.MtIdea{}, h, p, ra) == M.VRefuse{M.RIdea{}} : M.Verdict}

# M2: a shadow component is never applied automatically.
law shadow_never_allowed:
  for g: M.Gate
  for r: M.RevOrigin
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  for ra: M.RamTier
  {M.is_allow(M.decide_component(g, r, f, M.MtShadow{}, h, p, ra)) == False{} : Bool}

# D1 / public_ready: a pinned rev missing from origin is unavailable.
law rev_not_on_origin_unavailable:
  for g: M.Gate
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  for ra: M.RamTier
  {M.decide_component(g, M.OriginNo{}, f, M.MtStable{}, h, p, ra) == M.VUnavailable{M.RRevNotOnOrigin{}} : M.Verdict}

# D1: a dash rev that was never checked on origin is unavailable (rev_unverified),
# never deployed and never reported as "not on origin".
law dash_unverified_rev_unavailable:
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  for ra: M.RamTier
  {M.decide_component(M.GDash{}, M.OriginUnknown{}, f, M.MtStable{}, h, p, ra) == M.VUnavailable{M.RRevUnverified{}} : M.Verdict}

# D2: the legacy dash flavour is refused.
law legacy_dash_refused:
  for h: M.HwClass
  for p: M.PyWindow
  for ra: M.RamTier
  {M.decide_component(M.GDash{}, M.OriginYes{}, M.FLegacy{}, M.MtStable{}, h, p, ra) == M.VRefuse{M.RLegacyFlavour{}} : M.Verdict}

# Z1: z0intelligence on intel_mac is refused.
law z0int_intel_mac_refused:
  for f: M.Flavour
  for p: M.PyWindow
  for ra: M.RamTier
  {M.decide_component(M.GZ0int{}, M.OriginYes{}, f, M.MtStable{}, M.HwIntelMac{}, p, ra) == M.VRefuse{M.RIntelMac{}} : M.Verdict}

# Z1: z0intelligence without a python in [3.10, 3.14) is refused.
law z0int_python_window_refused:
  for f: M.Flavour
  for h: M.HwClass
  for ra: M.RamTier
  {M.is_refuse(M.decide_component(M.GZ0int{}, M.OriginYes{}, f, M.MtStable{}, h, M.PyImpossible{}, ra)) == True{} : Bool}

# §5.2: z0intelligence is never applied below 8 GiB RAM.
law z0int_ram_lt4_not_allowed:
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  {M.is_allow(M.decide_component(M.GZ0int{}, M.OriginYes{}, f, M.MtStable{}, h, p, M.RamLt4{})) == False{} : Bool}

law z0int_ram_4to8_not_allowed:
  for f: M.Flavour
  for h: M.HwClass
  for p: M.PyWindow
  {M.is_allow(M.decide_component(M.GZ0int{}, M.OriginYes{}, f, M.MtStable{}, h, p, M.Ram4to8{})) == False{} : Bool}

# Z2: the cpu class always takes the cpu torch index; so does any disk < 10 GiB.
law cpu_class_cpu_index:
  for c: Bool
  for r: Bool
  for d: Bool
  {M.decide_torch_index(M.HwCpu{}, c, r, d) == M.IxCpu{} : M.TorchIndex}

law low_disk_cpu_index_nvidia:
  for c: Bool
  for r: Bool
  {M.decide_torch_index(M.HwNvidia{}, c, r, True{}) == M.IxCpu{} : M.TorchIndex}

law intel_mac_no_torch:
  for c: Bool
  for r: Bool
  for d: Bool
  {M.decide_torch_index(M.HwIntelMac{}, c, r, d) == M.IxNone{} : M.TorchIndex}

# §5.2: below 3 GiB disk the auto profile refuses; intel_mac is never personal.
law tiny_disk_refuses_profile:
  for r: M.RamTier
  for h: M.HwClass
  for p: M.PyWindow
  {M.decide_profile(r, M.DiskLt3{}, h, p) == M.PfRefuse{} : M.Profile}

law intel_mac_profile_core:
  for r: M.RamTier
  for p: M.PyWindow
  {M.decide_profile(r, M.DiskGt40{}, M.HwIntelMac{}, p) == M.PfCore{} : M.Profile}
