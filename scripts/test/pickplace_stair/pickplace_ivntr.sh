export FD_EXEC_PATH=ext/downward
export PYTHONHASHSEED=0
export CUBLAS_WORKSPACE_CONFIG=:4096:8

for seed in 0
do
    echo "Running Seed $seed --------------------------------------"
    # Record start time
    start_time=$(date +%s)
    # low-level sampling is very hard for this environment
    if python3 predicators/main.py --env pickplace_stair --approach ivntr \
        --seed $seed --offline_data_method "demo" \
        --disable_harmlessness_check True \
        --exclude_domain_feat "none" \
        --excluded_predicates "HandSees,ViewableArm,HoldingTgt,HoldingStair,HandEmpty,Reachable,Near,OnGround,OnStair" \
        --neupi_pred_config "predicators/config/pickplace_stair/pred_all.yaml" \
        --neupi_do_normalization True \
        --neupi_gt_ae_matrix False \
        --sesame_task_planner "fdsat" \
        --num_train_tasks 2000 \
        --load_approach \
        --load_neupi_from_json True \
        --neupi_entropy_w 0.0 \
        --neupi_loss_w 1.0 \
        --bilevel_plan_without_sim False \
        --sesame_max_samples_per_step 50 \
        --timeout 50 \
        --domain_aaai_thresh 500000 \
        --spot_graph_nav_map "sqh_final" \
        --approach_dir "saved_approaches/open_models/pickplace_stair/ivntr_$seed" \
        --neupi_load_pretrained "saved_approaches/open_models/pickplace_stair/ivntr_$seed" \
        --log_file logs/pickplace_stair/ivntr_ood_$seed.log; then
        echo "Seed $seed completed successfully."
    else
        echo "Seed $seed encountered an error."
    fi

    # Record end time
    end_time=$(date +%s)

    # Calculate the duration in seconds
    runtime=$((end_time - start_time))

    # Convert to hours, minutes, and seconds
    hours=$((runtime / 3600))
    minutes=$(( (runtime % 3600) / 60 ))
    seconds=$((runtime % 60))

    # Output the total runtime
    echo "Seed $seed completed in: ${hours}h ${minutes}m ${seconds}s"

    # Record start time
    start_time=$(date +%s)
    # low-level sampling is very hard for this environment
    if python3 predicators/main.py --env pickplace_stair --approach ivntr \
        --seed $seed --offline_data_method "demo" \
        --disable_harmlessness_check True \
        --excluded_predicates "HandSees,ViewableArm,HoldingTgt,HoldingStair,HandEmpty,Reachable,Near,OnGround,OnStair" \
        --neupi_pred_config "predicators/config/pickplace_stair/pred_all.yaml" \
        --neupi_do_normalization True \
        --neupi_gt_ae_matrix False \
        --exclude_domain_feat "none" \
        --sesame_task_planner "fdsat" \
        --num_train_tasks 2000 \
        --load_data \
        --neupi_entropy_w 0.0 \
        --neupi_loss_w 1.0 \
        --bilevel_plan_without_sim False \
        --load_approach \
        --load_neupi_from_json True \
        --sesame_max_samples_per_step 50 \
        --timeout 50 \
        --in_domain_test True \
        --spot_graph_nav_map "sqh_final" \
        --approach_dir "saved_approaches/open_models/pickplace_stair/ivntr_$seed" \
        --log_file logs/pickplace_stair/ivntr_in_domain_$seed.log; then
        echo "Seed $seed completed successfully."
    else
        echo "Seed $seed encountered an error."
    fi

    # Record end time
    end_time=$(date +%s)

    # Calculate the duration in seconds
    runtime=$((end_time - start_time))

    # Convert to hours, minutes, and seconds
    hours=$((runtime / 3600))
    minutes=$(( (runtime % 3600) / 60 ))
    seconds=$((runtime % 60))

    # Output the total runtime
    echo "Seed $seed completed in: ${hours}h ${minutes}m ${seconds}s"
done