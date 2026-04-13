#!/bin/bash
# Run Grounding DINO proposals for 100 images per faction
# Settings: threshold=0.25, prompt="miniature . figurine", nms-threshold=0.5 (defaults)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_ROOT/scripts/dino_run.log"
VENV="$PROJECT_ROOT/yolo_env/bin/activate"

FACTIONS=(
  adepta_sororitas
  adeptus_mechanicus
  black_templars
  blood_angels
  chaos_daemons
  chaos_knights
  chaos_space_marines
  custodes
  dark_angels
  death_guard
  deathwatch
  drukhari
  eldar
  emperors_children
  genestealer_cult
  grey_knights
  harlequins
  hormagaunts
  imperial_agents
  imperial_guard
  imperial_knights
  leagues_of_votann
  necrons
  orks
  space_marines
  space_wolves
  tau_empire
  thousand_sons
  tyranid_ripper_swarm
  tyranids
  world_eaters
  ynnari
)

source "$VENV"

echo "======================================" | tee -a "$LOG"
echo "DINO batch run started: $(date)" | tee -a "$LOG"
echo "Factions: ${#FACTIONS[@]} | Limit: 100 each | Total: ~$((${#FACTIONS[@]} * 100))" | tee -a "$LOG"
echo "======================================" | tee -a "$LOG"

DONE=0
SKIPPED=0

for faction in "${FACTIONS[@]}"; do
  echo "" | tee -a "$LOG"
  echo "--- [$((DONE + SKIPPED + 1))/${#FACTIONS[@]}] $faction $(date +%H:%M:%S) ---" | tee -a "$LOG"

  python "$PROJECT_ROOT/scripts/grounding_dino_propose.py" \
    --faction "$faction" \
    --limit 100 \
    2>&1 | tee -a "$LOG"

  DONE=$((DONE + 1))
done

echo "" | tee -a "$LOG"
echo "======================================" | tee -a "$LOG"
echo "DONE: $(date) | $DONE factions processed" | tee -a "$LOG"
echo "======================================" | tee -a "$LOG"
