# Proofs for the exact LAWS.bend signatures. Do not weaken LAWS to make --verdict pass.
import Base
import ./MODEL.bend as M
import ./LAWS.bend as Laws

def Laws.stale_never_admits(u, p, w):
  {==}

def Laws.at_cap_never_admits(f, p, w):
  match f:
    case M.FFresh{}:
      {==}
    case M.FStale{}:
      {==}

def Laws.hot_bulk_never_admits(f, u):
  match f:
    case M.FFresh{}:
      match u:
        case M.UUnder{}:
          {==}
        case M.UAtCap{}:
          {==}
    case M.FStale{}:
      {==}

def Laws.owner_keeps_opus_when_hot():
  {==}

def Laws.fresh_cool_admits():
  {==}

def Laws.fresh_unknown_admits():
  {==}

def Laws.none_admitted_routes_free():
  {==}

def Laws.admitted_routes_paid():
  {==}

def Laws.hot_bulk_routes_free(f, u):
  match f:
    case M.FFresh{}:
      match u:
        case M.UUnder{}:
          {==}
        case M.UAtCap{}:
          {==}
    case M.FStale{}:
      {==}
