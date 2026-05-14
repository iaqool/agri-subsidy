# Dala Network — Anchor program (`agri_subsidy`)

Source build of the M-of-N quorum drought-oracle program. Deployed to Devnet at
`2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK` (pool
`AxnVgXUfeDk7nXXjhjvVuWPEvxh2SXBbDieUxfvJ64KL`), currently initialized with
`quorum = 1` for the live demo. See `programs/agri_subsidy/src/lib.rs`.

## Layout

```
contracts/
├── Anchor.toml                 # workspace + scripts + [test] config
├── Cargo.toml, Cargo.lock      # rust workspace
├── package.json, tsconfig.json # mocha + ts-mocha harness
├── programs/agri_subsidy/      # the on-chain program
└── tests/agri_subsidy.test.ts  # adversarial mocha suite (see below)
```

## Tests

`tests/agri_subsidy.test.ts` is the regression net for the M-of-N quorum,
parameterized policy (`min_score`, `max_amount_per_payout`), and idempotent
attestation logic. It exercises the on-chain program against an in-process
`solana-test-validator`.

### Run the full suite locally

```bash
cd contracts
npm install
anchor test --provider.cluster localnet
```

You need:

* `solana-cli 1.18.x` (matches `Anchor.toml [toolchain]`)
* `anchor-cli 0.29.0` (recommended install: `avm install 0.29.0 && avm use 0.29.0`)
* `rustc` (any recent stable — anchor will use `cargo-build-sbf` for the BPF target)
* node `>=18`

`anchor test` will boot a local validator, deploy the program, and run the
mocha suite. First run is slow (BPF compile + platform-tools download); reruns
are cached.

### Why the mocha suite is not run in CI

CI only validates that `npm install` succeeds against the harness in
`package.json` / `tsconfig.json` (see `.github/workflows/ci.yml ::
contracts-tests`). The full `anchor test` is **not** run in CI today because
of a known toolchain triangle:

* `anchor-lang 0.29` transitive deps (`toml_datetime`, …) require `edition2024`,
  stabilized in `rustc 1.85`.
* `solana-cli 1.18.17` ships `cargo-build-sbf` with `rustc 1.79`, which can
  compile neither `edition2024` crates nor read a v4 `Cargo.lock` (v4 requires
  cargo `≥1.81`).
* The host `cargo` on `ubuntu-24.04` runners is `1.95` and writes v4 locks by
  default, poisoning the lockfile for the BPF cargo on every host-cargo step.

Unblocking the BPF build in CI requires one of:

1. Bumping the program to anchor `0.30+` and `agave 2.x+` (rustc `1.84+`). This
   is a program-code change and is tracked as a follow-up.
2. Pinning several transitive deps below their `edition2024` cut. Also tracked.

Until that work lands, `cargo +stable check --package agri_subsidy` in the
`contracts` CI job is the smoke gate; the mocha suite must be run locally
before changes to `lib.rs` are merged. See `MEMORY.md` for the active
decision log.
