# Cell evaluation: before / after fine-tune

Simulation (MuJoCo, YAM arms), evaluation seeds < 1000 (training 4000+), same scene per task x seed for every model, training prompts. Success = part resting in the target zone (cnc_expert.task_done) AND the arm's gripper open, stable for 3 checks (0.4 s); time from the model's first answer. Primary: paired success (exact McNemar); secondary: paired time where both succeed, runs with contact. Scoring: FIRST attempt per scene (corrected 22.11. 10:00, Codex review): an action the vendor check rejects (e.g. gripper 1.05-1.09 outside 0..1) is the model's failure, not retried; only infrastructure errors are retried once and excluded. Contact runs = runs with at least one detected contact, not a collision count. Expert = reference only (its success also requires no contact and a retreat). Contact = arm–cell penetration > 0.5 mm; arm–arm and part–environment are not checked. Wilson 95 % intervals.

Rate check: training data moves 0.00959 rad per frame at 10 fps while the arm moves (= 0.00480 per row at 20 rows/s, 0.00320 at 30). Compare with each model's 'joint change per returned row' to pick --rate.

### expert  (expert)

- Success: **39/40 (87%–100%)**; collision-free success: **39/40 (87%–100%)**
- Runs with arm–cell contact: 1/40 (0%–13%)
- Median time to done: 14.5 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 0 action-error attempts; calibration, warm-up and training not included): 0.000 $, 0.0000 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 10/10 (72%–100%) | 10/10 (72%–100%) | 0 | success 10 |
| sort_cube | 10/10 (72%–100%) | 10/10 (72%–100%) | 0 | success 10 |
| cnc_load | 10/10 (72%–100%) | 10/10 (72%–100%) | 0 | success 10 |
| cnc_unload | 9/10 (60%–98%) | 9/10 (60%–98%) | 1 | collision 1, success 9 |

### beta-main  (dreamlabs/dream-1-beta)

- Success: **6/40 (7%–29%)**; collision-free success: **6/40 (7%–29%)**
- Runs with arm–cell contact: 8/40 (10%–35%)
- Median time to done: 29.6 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 0 action-error attempts; calibration, warm-up and training not included): 1.011 $, 0.1685 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 0/10 (0%–28%) | 0/10 (0%–28%) | 7 | timeout_dropped 3, timeout_no_grasp 7 |
| sort_cube | 2/10 (6%–51%) | 2/10 (6%–51%) | 0 | success 2, timeout_dropped 3, timeout_no_grasp 5 |
| cnc_load | 3/10 (11%–60%) | 3/10 (11%–60%) | 0 | success 3, timeout_dropped 1, timeout_no_grasp 6 |
| cnc_unload | 1/10 (2%–40%) | 1/10 (2%–40%) | 1 | success 1, timeout_dropped 5, timeout_no_grasp 1, timeout_placed_not_released 3 |

- Mean joint change per returned row: 0.00360 rad

### ft-main  (dream-1-ft:317db52a-yam-cells-c500)

- Success: **14/40 (22%–50%)**; collision-free success: **13/40 (20%–48%)**
- Runs with arm–cell contact: 17/40 (29%–58%)
- Median time to done: 23.6 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 3 action-error attempts; calibration, warm-up and training not included): 1.800 $, 0.1286 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 2/10 (6%–51%) | 2/10 (6%–51%) | 4 | action_error 1, success 2, timeout_dropped 1, timeout_no_grasp 6 |
| sort_cube | 2/10 (6%–51%) | 2/10 (6%–51%) | 5 | action_error 1, success 2, timeout_no_grasp 7 |
| cnc_load | 7/10 (40%–89%) | 7/10 (40%–89%) | 1 | success 7, timeout_dropped 2, timeout_placed_not_released 1 |
| cnc_unload | 3/10 (11%–60%) | 2/10 (6%–51%) | 7 | success 3, timeout_dropped 3, timeout_no_grasp 4 |

- Mean joint change per returned row: 0.00301 rad

### ft-rep-main  (dream-1-ft:317db52a-yam-cells-c500-rep)

- Success: **17/40 (29%–58%)**; collision-free success: **15/40 (24%–53%)**
- Runs with arm–cell contact: 15/40 (24%–53%)
- Median time to done: 24.6 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 24 action-error attempts; calibration, warm-up and training not included): 1.803 $, 0.1061 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 5/10 (24%–76%) | 4/10 (17%–69%) | 6 | action_error 1, success 5, timeout_no_grasp 4 |
| sort_cube | 0/10 (0%–28%) | 0/10 (0%–28%) | 4 | action_error 9, timeout_no_grasp 1 |
| cnc_load | 10/10 (72%–100%) | 10/10 (72%–100%) | 0 | success 10 |
| cnc_unload | 2/10 (6%–51%) | 1/10 (2%–40%) | 5 | action_error 4, success 2, timeout_dropped 3, timeout_no_grasp 1 |

- Mean joint change per returned row: 0.00323 rad

### ft-lr3-main  (dream-1-ft:317db52a-yam-cells-c500-lr3)

- Success: **20/40 (35%–65%)**; collision-free success: **18/40 (31%–60%)**
- Runs with arm–cell contact: 13/40 (20%–48%)
- Median time to done: 18.7 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 8 action-error attempts; calibration, warm-up and training not included): 1.481 $, 0.0741 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 9/10 (60%–98%) | 7/10 (40%–89%) | 3 | success 9, timeout_dropped 1 |
| sort_cube | 0/10 (0%–28%) | 0/10 (0%–28%) | 5 | action_error 6, timeout_no_grasp 4 |
| cnc_load | 1/10 (2%–40%) | 1/10 (2%–40%) | 5 | action_error 2, success 1, timeout_dropped 4, timeout_placed_not_released 3 |
| cnc_unload | 10/10 (72%–100%) | 10/10 (72%–100%) | 0 | success 10 |

- Motion (exploratory, 40 runs): median release drop 0.0 cm, fall speed 0.22 m/s (n=28 releases); time to lift 9.2 s (n=30); joint speed first 3 s 0.191 rad/s, overall 0.194 rad/s; jerk RMS 33 rad/s³; joint path 12.2 rad

- Mean joint change per returned row: 0.00326 rad

### ft-b05-main  (dream-1-ft:317db52a-yam-cells-c500-b05)

- Success: **6/40 (7%–29%)**; collision-free success: **5/40 (5%–26%)**
- Runs with arm–cell contact: 14/40 (22%–50%)
- Median time to done: 23.2 s
- Cost (tariff estimate of answered calls, incl. 0 infrastructure-error attempts (retried) and 23 action-error attempts; calibration, warm-up and training not included): 1.400 $, 0.2333 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 4/10 (17%–69%) | 4/10 (17%–69%) | 5 | action_error 1, success 4, timeout_dropped 2, timeout_no_grasp 3 |
| sort_cube | 0/10 (0%–28%) | 0/10 (0%–28%) | 2 | action_error 8, timeout_no_grasp 2 |
| cnc_load | 0/10 (0%–28%) | 0/10 (0%–28%) | 4 | action_error 7, timeout_dropped 3 |
| cnc_unload | 2/10 (6%–51%) | 1/10 (2%–40%) | 3 | action_error 7, success 2, timeout_no_grasp 1 |

- Motion (exploratory, 40 runs): median release drop 0.1 cm, fall speed 0.02 m/s (n=7 releases); time to lift 11.0 s (n=17); joint speed first 3 s 0.032 rad/s, overall 0.198 rad/s; jerk RMS 48 rad/s³; joint path 11.5 rad

- Mean joint change per returned row: 0.00363 rad

### beta-main2  (dreamlabs/dream-1-beta)

- Success: **7/40 (9%–32%)**; collision-free success: **7/40 (9%–32%)**
- Runs with arm–cell contact: 5/40 (5%–26%)
- Median time to done: 39.8 s
- Cost (tariff estimate of answered calls, incl. 1 infrastructure-error attempts (retried) and 0 action-error attempts; calibration, warm-up and training not included): 1.033 $, 0.1476 $ per success

| Task | Success | Collision-free | Contact runs | Outcomes |
|---|---|---|---|---|
| sort_round | 3/10 (11%–60%) | 3/10 (11%–60%) | 5 | success 3, timeout_dropped 1, timeout_no_grasp 6 |
| sort_cube | 0/10 (0%–28%) | 0/10 (0%–28%) | 0 | timeout_dropped 4, timeout_no_grasp 5, timeout_placed_not_released 1 |
| cnc_load | 3/10 (11%–60%) | 3/10 (11%–60%) | 0 | success 3, timeout_dropped 1, timeout_no_grasp 6 |
| cnc_unload | 1/10 (2%–40%) | 1/10 (2%–40%) | 0 | success 1, timeout_dropped 4, timeout_no_grasp 2, timeout_placed_not_released 3 |

- Motion (exploratory, 40 runs): median release drop 0.0 cm, fall speed 0.00 m/s (n=15 releases); time to lift 25.0 s (n=21); joint speed first 3 s 0.038 rad/s, overall 0.164 rad/s; jerk RMS 48 rad/s³; joint path 14.5 rad

- Mean joint change per returned row: 0.00354 rad

## Paired: beta-main → ft-main (40 identical scenes)

- Success 6/40 (7%–29%) → 14/40 (22%–50%)
- **Paired (primary): fail→success 11, success→fail 3; exact McNemar p = 0.057** → no proven difference
- Unpaired Wilson intervals overlap (descriptive only)
- Time to done on scenes both solved (n=3): median change -1.4 s
- Runs with arm–cell contact: 8 → 17
- Fail→success scenes: cnc_load seed 2, cnc_load seed 4, cnc_load seed 7, cnc_load seed 9, cnc_unload seed 1, cnc_unload seed 3, cnc_unload seed 8, sort_cube seed 3, sort_cube seed 9, sort_round seed 7, sort_round seed 9
- Success→fail scenes: cnc_unload seed 9, sort_cube seed 0, sort_cube seed 1

## Paired: beta-main → ft-rep-main (40 identical scenes)

- Success 6/40 (7%–29%) → 17/40 (29%–58%)
- **Paired (primary): fail→success 14, success→fail 3; exact McNemar p = 0.013** → paired difference on these simulated test scenes
- Unpaired Wilson intervals overlap (descriptive only)
- Time to done on scenes both solved (n=3): median change +0.4 s
- Runs with arm–cell contact: 8 → 15
- Fail→success scenes: cnc_load seed 2, cnc_load seed 4, cnc_load seed 5, cnc_load seed 6, cnc_load seed 7, cnc_load seed 8, cnc_load seed 9, cnc_unload seed 4, cnc_unload seed 7, sort_round seed 1, sort_round seed 2, sort_round seed 3, sort_round seed 7, sort_round seed 8
- Success→fail scenes: cnc_unload seed 9, sort_cube seed 0, sort_cube seed 1

## Paired: beta-main → ft-lr3-main (40 identical scenes)

- Success 6/40 (7%–29%) → 20/40 (35%–65%)
- **Paired (primary): fail→success 19, success→fail 5; exact McNemar p = 0.007** → paired difference on these simulated test scenes
- Unpaired Wilson intervals do not overlap (descriptive only)
- Time to done on scenes both solved (n=1): median change -12.6 s
- Runs with arm–cell contact: 8 → 13
- Fail→success scenes: cnc_load seed 2, cnc_unload seed 0, cnc_unload seed 1, cnc_unload seed 2, cnc_unload seed 3, cnc_unload seed 4, cnc_unload seed 5, cnc_unload seed 6, cnc_unload seed 7, cnc_unload seed 8, sort_round seed 0, sort_round seed 1, sort_round seed 2, sort_round seed 4, sort_round seed 5, sort_round seed 6, sort_round seed 7, sort_round seed 8, sort_round seed 9
- Success→fail scenes: cnc_load seed 0, cnc_load seed 1, cnc_load seed 3, sort_cube seed 0, sort_cube seed 1

## Paired: beta-main → ft-b05-main (40 identical scenes)

- Success 6/40 (7%–29%) → 6/40 (7%–29%)
- **Paired (primary): fail→success 6, success→fail 6; exact McNemar p = 1.000** → no proven difference
- Unpaired Wilson intervals overlap (descriptive only)
- Time to done on scenes both solved (n=0): median change –
- Runs with arm–cell contact: 8 → 14
- Fail→success scenes: cnc_unload seed 6, cnc_unload seed 8, sort_round seed 1, sort_round seed 2, sort_round seed 7, sort_round seed 8
- Success→fail scenes: cnc_load seed 0, cnc_load seed 1, cnc_load seed 3, cnc_unload seed 9, sort_cube seed 0, sort_cube seed 1

## Paired: beta-main → beta-main2 (40 identical scenes)

- Success 6/40 (7%–29%) → 7/40 (9%–32%)
- **Paired (primary): fail→success 6, success→fail 5; exact McNemar p = 1.000** → no proven difference
- Unpaired Wilson intervals overlap (descriptive only)
- Time to done on scenes both solved (n=1): median change -4.4 s
- Runs with arm–cell contact: 8 → 5
- Fail→success scenes: cnc_load seed 4, cnc_load seed 7, cnc_unload seed 5, sort_round seed 5, sort_round seed 6, sort_round seed 8
- Success→fail scenes: cnc_load seed 0, cnc_load seed 1, cnc_unload seed 9, sort_cube seed 0, sort_cube seed 1
