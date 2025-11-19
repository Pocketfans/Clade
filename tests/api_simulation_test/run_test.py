import httpx
import time
import json
import os
import sys
import logging
from pathlib import Path
from statistics import mean

# Configuration
BASE_URL = "http://localhost:8000/api"
SAVE_NAME = f"sim_earth_evo_{int(time.time())}"
TOTAL_TURNS = 15
TIMEOUT_SETTINGS = httpx.Timeout(120.0, connect=10.0) # Increased timeout for heavy AI ops

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tests/api_simulation_test/earth_evo_log.txt", mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger("SimEarth")

def check_server():
    logger.info("Checking server connectivity...")
    for i in range(5):
        try:
            resp = httpx.get(f"{BASE_URL}/saves/list", timeout=5)
            if resp.status_code == 200:
                logger.info("Server is online.")
                return True
        except Exception:
            pass
        logger.info(f"Waiting for server... ({i+1}/5)")
        time.sleep(2)
    return False

def run_earth_simulation():
    logger.info("=== STARTING 'EARTH-LIKE' EVOLUTION SIMULATION (15 TURNS) ===")
    
    if not check_server():
        logger.error("CRITICAL: Backend server is not reachable.")
        return

    client = httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SETTINGS)

    # 1. Create New Game Save (Scenario: Original Continent / Default)
    logger.info(f"[Setup] Creating new save: {SAVE_NAME}")
    try:
        resp = client.post("/saves/create", json={"save_name": SAVE_NAME, "scenario": "原初大陆"})
        if resp.status_code != 200:
            logger.error(f"Failed to create save: {resp.text}")
            return
        
        initial_state = client.get("/species/list").json()
        logger.info(f"[Setup] Initial World: {len(initial_state['species'])} species.")
        for s in initial_state['species']:
            logger.info(f"  - {s['latin_name']} ({s['common_name']}): {s['population']} | {s['ecological_role']}")
            
    except Exception as e:
        logger.error(f"[Setup] Error: {e}")
        return

    # Data Collection
    history_events = []
    species_count_log = []
    
    # 2. Run Simulation Loop
    # Strategy: 
    # - Early phase: High population growth
    # - Mid phase: Severe environmental selection to force speciation
    
    for turn in range(1, TOTAL_TURNS + 1):
        try:
            start_ts = time.time()
            payload = {"rounds": 1, "pressures": []}
            
            # --- DYNAMIC PRESSURE SCHEDULE ---
            # Turn 5: Early cooling to stimulate adaptation
            if turn == 5:
                logger.info(">>> EVENT: COOLING PERIOD (Intensity 5)")
                payload["pressures"].append({
                    "kind": "temperature", 
                    "intensity": 5, 
                    "narrative_note": "Global temperature drops moderately."
                })
            
            # Turn 10: Ice Age (Filter weak species)
            elif turn == 10:
                logger.info(">>> EVENT: THE GREAT FREEZE (Intensity 9)")
                payload["pressures"].append({
                    "kind": "temperature", 
                    "intensity": 9, 
                    "narrative_note": "Global temperature plummets drastically."
                })
            
            # Turn 12: Volcanic Activity (Create new niches)
            elif turn == 12:
                logger.info(">>> EVENT: VOLCANIC ACTIVITY (Intensity 7)")
                payload["pressures"].append({
                    "kind": "volcano", 
                    "intensity": 7,
                    "narrative_note": "Local volcanic eruptions create new land."
                })

            # Run Turn
            run_resp = client.post("/turns/run", json=payload)
            if run_resp.status_code != 200:
                logger.error(f"[Turn {turn}] Failed: {run_resp.text}")
                break
            
            turn_reports = run_resp.json()
            if not turn_reports:
                logger.error(f"[Turn {turn}] No report returned.")
                continue
                
            turn_report = turn_reports[0]
            elapsed = time.time() - start_ts
            
            # Fetch Updated Species List
            sp_list = client.get("/species/list").json()['species']
            
            # Log Progress
            new_speciation = len(turn_report.get('branching_events', []))
            extinctions = sum(1 for s in turn_report.get('species', []) if s['status'] == 'extinct')
            map_changes = len(turn_report.get('map_changes', []))
            major_events = len(turn_report.get('major_events', []))
            
            logger.info(f"--- Turn {turn} Summary ---")
            logger.info(f"Time: {elapsed:.2f}s | Pop: {sum(s['population'] for s in sp_list):,} | Species: {len(sp_list)}")
            
            if map_changes > 0:
                logger.info(f"  [Map Changes] {map_changes} events recorded.")
                for change in turn_report.get('map_changes', [])[:3]:
                    logger.info(f"    - {change['stage']}: {change['description']}")
            
            if major_events > 0:
                logger.info(f"  [Major Events] {major_events} events recorded.")
                for event in turn_report.get('major_events', [])[:3]:
                    logger.info(f"    - {event['severity']}: {event['description']}")

            if new_speciation > 0:
                logger.info(f"  [Speciation] {new_speciation} new species!")
                for evt in turn_report['branching_events']:
                    logger.info(f"    -> {evt['new_lineage']} from {evt['parent_lineage']} ({evt['reason']})")
            
            if extinctions > 0:
                logger.info(f"  [Extinction] {extinctions} species extinct.")
                for s in turn_report.get('species', []):
                    if s['status'] == 'extinct':
                        logger.info(f"    -> {s['common_name']} ({s['lineage_code']})")

            species_count_log.append(len(sp_list))
            history_events.append(turn_report)
                
        except Exception as e:
            logger.error(f"[Turn {turn}] Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            break

    # 3. Final Analysis
    analyze_earth_run(client, species_count_log)

def analyze_earth_run(client, count_log):
    logger.info("\n=== FINAL EVOLUTIONARY ANALYSIS ===")
    
    # Fetch final state
    try:
        final_list = client.get("/species/list").json()['species']
        
        # 1. Diversity Check
        initial_count = 3 # We know we started with 3
        final_count = len(final_list)
        logger.info(f"Species Diversity: {initial_count} -> {final_count}")
        
        if final_count > initial_count:
            logger.info("[PASS] Adaptive radiation occurred.")
        elif final_count < initial_count:
            logger.warning("[WARN] Mass extinction without recovery.")
        else:
            logger.warning("[WARN] Stasis. No net evolution.")
            
        # 2. Trophic Structure Check
        roles = {}
        for s in final_list:
            r = s.get('ecological_role', 'unknown')
            roles[r] = roles.get(r, 0) + 1
            
        logger.info(f"Ecological Roles Distribution (Count): {roles}")
        
        has_consumers = roles.get('carnivore', 0) > 0 or roles.get('herbivore', 0) > 0 or roles.get('omnivore', 0) > 0
        if has_consumers:
            logger.info("[PASS] Consumers exist in the ecosystem.")
        else:
            logger.error("[FAIL] Ecosystem lacks consumers (Only producers?).")

        # 3. Check Lineage of B1 (Protoflagella)
        # We want to see if B1 evolved into higher forms
        lineage_tree = client.get("/lineage").json()
        b_descendants = [
            node for node in lineage_tree['nodes'] 
            if node['lineage_code'].startswith('B') and len(node['lineage_code']) > 2
        ]
        
        if b_descendants:
            logger.info(f"[PASS] Protoflagella (B) lineage evolved {len(b_descendants)} new species.")
            logger.info(f"      Example: {b_descendants[0]['latin_name']} ({b_descendants[0]['common_name']})")
        else:
            logger.info("[INFO] Protoflagella (B) lineage did not branch out significantly.")

        logger.info(f"Log saved to tests/api_simulation_test/earth_evo_log.txt")
    except Exception as e:
        logger.error(f"Analysis failed: {e}")

if __name__ == "__main__":
    run_earth_simulation()
