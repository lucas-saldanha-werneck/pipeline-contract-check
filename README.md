# pipeline-contract-check

Independent demo, not affiliated with Jobgether (cliente não diz).

A small command-line tool that checks a CSV extract against a JSON data contract. It is plain Python with no dependencies. I wrote it as a sample of the kind of guard I put at the start of a data pipeline: before a file goes into a model or an LLM prompt, check that it is the file you expected.

## What it checks

- Missing and unexpected columns
- Empty values in columns that are not nullable
- Values that do not parse as int, float or date
- Min/max limits and lists of allowed values
- Repeated keys (`unique_key`)
- Freshness: how old the newest date in a column is
- Row count against an expected number, with a percent tolerance

The exit code is 1 when anything is found, 0 when the file is clean, so it can stop a job in CI or cron.

## Run it

```
pip install -e .
contract-check examples/orders_sample.csv examples/contract.json --as-of 2026-11-23
contract-check examples/orders_sample.csv examples/contract.json --json
```

Without installing: `PYTHONPATH=src python -m contractcheck.cli <csv> <contract>`.

The data in `examples/` is invented. It has one planted problem per check so you can see the output.

## Contract format

See `examples/contract.json`. Each column has a `type` (`int`, `float`, `date`, `str`) and optional `nullable`, `min`, `max`, `allowed`. Dates use `YYYY-MM-DD`.

## What was tested

- 14 pytest tests, all offline, run in GitHub Actions on every push (`.github/workflows/test.yml`).
- Each check has a test for a failing case. Clean data, a nullable column and the exit codes have one too.
- On the invented sample file, the tool reports five problems: an empty customer, a status outside the list, a non-numeric amount, a negative amount and a repeated order id.

## What was not tested

- Real data. Everything ran on small invented files.
- Large files. The CSV is read into memory, so a file of many millions of rows would be a problem.
- Other encodings and delimiters. It expects UTF-8 and commas.
- Python versions other than 3.12 in CI and 3.15 on my machine.
- Time zones. Dates have no time part.
