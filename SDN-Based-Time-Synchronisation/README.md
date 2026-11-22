# SDN-Based Time Synchronisation


## Re-running the result analysis

The analysis script is `Source_Code/final_analysis.py`. It reads the six trial
measurement CSV files from `Results/`, recalculates per-trial and per-scenario
statistics, and creates three comparison graphs.

Install the graphing dependency:

```bash
python -m pip install matplotlib
```

Run from the project root:

```bash
python Source_Code/final_analysis.py
```

Generated summaries and graphs are saved under
`Results/Final_Comparison/Generated_Analysis/`. The script does not overwrite
the original submitted summaries or graphs. By default, it expects 20 requests
per trial, matching the experiment methodology in the technical report.
