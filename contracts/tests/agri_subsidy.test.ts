import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { AgriSubsidy } from "../target/types/agri_subsidy";
import { PublicKey, Keypair, LAMPORTS_PER_SOL } from "@solana/web3.js";
import { assert } from "chai";

const EVAL_ID_LEN = 16;
const MIN_SCORE = 55;
const MAX_AMOUNT = new anchor.BN(5 * LAMPORTS_PER_SOL);

function evalIdFromString(s: string): number[] {
  const buf = Buffer.alloc(EVAL_ID_LEN);
  buf.write(s, 0, "utf8");
  return Array.from(buf);
}

describe("agri_subsidy", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.AgriSubsidy as Program<AgriSubsidy>;
  const authority = provider.wallet as anchor.Wallet;

  const oracle = Keypair.generate();
  const oracle2 = Keypair.generate();
  const oracle3 = Keypair.generate();

  const farmer = Keypair.generate();
  const farmer2 = Keypair.generate();
  const farmer3 = Keypair.generate();

  let poolPda: PublicKey;
  let poolBump: number;
  let farmerAccountPda: PublicKey;
  let farmer2Pda: PublicKey;
  let farmer3Pda: PublicKey;

  before(async () => {
    [poolPda, poolBump] = PublicKey.findProgramAddressSync(
      [Buffer.from("subsidy_pool"), authority.publicKey.toBuffer()],
      program.programId
    );
    [farmerAccountPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("farmer"), poolPda.toBuffer(), farmer.publicKey.toBuffer()],
      program.programId
    );
    [farmer2Pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("farmer"), poolPda.toBuffer(), farmer2.publicKey.toBuffer()],
      program.programId
    );
    [farmer3Pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("farmer"), poolPda.toBuffer(), farmer3.publicKey.toBuffer()],
      program.programId
    );

    for (const kp of [oracle, oracle2, oracle3]) {
      await provider.connection.confirmTransaction(
        await provider.connection.requestAirdrop(kp.publicKey, 2 * LAMPORTS_PER_SOL)
      );
    }
    for (const kp of [farmer, farmer2, farmer3]) {
      await provider.connection.confirmTransaction(
        await provider.connection.requestAirdrop(kp.publicKey, 0.1 * LAMPORTS_PER_SOL)
      );
    }
  });

  it("initialises a pool with parametrised policy and a single oracle", async () => {
    await program.methods
      .initializeSubsidyPool(poolBump, MIN_SCORE, MAX_AMOUNT, 1)
      .accounts({
        authority: authority.publicKey,
        oracle: oracle.publicKey,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    const pool = await program.account.subsidyPool.fetch(poolPda);
    assert.equal(pool.authority.toString(), authority.publicKey.toString());
    assert.equal(pool.oracleCount, 1);
    assert.equal(pool.quorum, 1);
    assert.equal(pool.minScore, MIN_SCORE);
    assert.equal(pool.maxAmountPerPayout.toString(), MAX_AMOUNT.toString());
    assert.equal(pool.oracles[0].toString(), oracle.publicKey.toString());
    assert.isTrue(pool.isActive);
  });

  it("registers two more oracles via register_oracle", async () => {
    await program.methods
      .registerOracle()
      .accounts({
        authority: authority.publicKey,
        newOracle: oracle2.publicKey,
        pool: poolPda,
      })
      .rpc();

    await program.methods
      .registerOracle()
      .accounts({
        authority: authority.publicKey,
        newOracle: oracle3.publicKey,
        pool: poolPda,
      })
      .rpc();

    const pool = await program.account.subsidyPool.fetch(poolPda);
    assert.equal(pool.oracleCount, 3);
    assert.equal(pool.oracles[1].toString(), oracle2.publicKey.toString());
    assert.equal(pool.oracles[2].toString(), oracle3.publicKey.toString());
  });

  it("rejects duplicate oracle registration", async () => {
    try {
      await program.methods
        .registerOracle()
        .accounts({
          authority: authority.publicKey,
          newOracle: oracle2.publicKey,
          pool: poolPda,
        })
        .rpc();
      assert.fail("Should have thrown OracleAlreadyRegistered");
    } catch (e: any) {
      assert.include(e.message, "OracleAlreadyRegistered");
    }
  });

  it("registers a farmer", async () => {
    await program.methods
      .registerFarmer("UA-ZAPORIZHZHIA")
      .accounts({
        payer: authority.publicKey,
        farmerWallet: farmer.publicKey,
        farmerAccount: farmerAccountPda,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    const farmerAcc = await program.account.farmerAccount.fetch(farmerAccountPda);
    assert.equal(farmerAcc.region, "UA-ZAPORIZHZHIA");
    assert.deepEqual(farmerAcc.status, { pending: {} });
  });

  it("releases funds via single-oracle path while quorum=1", async () => {
    const fundTx = await provider.connection.requestAirdrop(
      poolPda,
      4 * LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(fundTx);

    const before = await provider.connection.getBalance(farmer.publicKey);
    const amount = new anchor.BN(1.5 * LAMPORTS_PER_SOL);

    await program.methods
      .releaseFundsByOracle(amount, 78)
      .accounts({
        oracle: oracle.publicKey,
        farmerWallet: farmer.publicKey,
        farmerAccount: farmerAccountPda,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([oracle])
      .rpc();

    const farmerAcc = await program.account.farmerAccount.fetch(farmerAccountPda);
    assert.deepEqual(farmerAcc.status, { approved: {} });
    assert.equal(farmerAcc.score, 78);

    const after = await provider.connection.getBalance(farmer.publicKey);
    assert.isTrue(after > before);
  });

  it("rejects single-oracle release when score below pool.min_score", async () => {
    await program.methods
      .registerFarmer("KZ-AKTOBE")
      .accounts({
        payer: authority.publicKey,
        farmerWallet: farmer2.publicKey,
        farmerAccount: farmer2Pda,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    try {
      await program.methods
        .releaseFundsByOracle(new anchor.BN(1 * LAMPORTS_PER_SOL), 40)
        .accounts({
          oracle: oracle.publicKey,
          farmerWallet: farmer2.publicKey,
          farmerAccount: farmer2Pda,
          pool: poolPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([oracle])
        .rpc();
      assert.fail("Should have thrown ScoreBelowThreshold");
    } catch (e: any) {
      assert.include(e.message, "ScoreBelowThreshold");
    }
  });

  it("rejects unauthorized oracle (not registered on pool)", async () => {
    const fakeOracle = Keypair.generate();
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(fakeOracle.publicKey, 0.5 * LAMPORTS_PER_SOL)
    );

    try {
      await program.methods
        .releaseFundsByOracle(new anchor.BN(1 * LAMPORTS_PER_SOL), 90)
        .accounts({
          oracle: fakeOracle.publicKey,
          farmerWallet: farmer2.publicKey,
          farmerAccount: farmer2Pda,
          pool: poolPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([fakeOracle])
        .rpc();
      assert.fail("Should have thrown UnauthorizedOracle");
    } catch (e: any) {
      assert.include(e.message, "UnauthorizedOracle");
    }
  });

  it("update_quorum: switches the pool to 2-of-3", async () => {
    await program.methods
      .updateQuorum(2)
      .accounts({
        authority: authority.publicKey,
        pool: poolPda,
      })
      .rpc();

    const pool = await program.account.subsidyPool.fetch(poolPda);
    assert.equal(pool.quorum, 2);
    assert.equal(pool.oracleCount, 3);
  });

  it("blocks single-oracle path once quorum > 1", async () => {
    try {
      await program.methods
        .releaseFundsByOracle(new anchor.BN(1 * LAMPORTS_PER_SOL), 80)
        .accounts({
          oracle: oracle.publicKey,
          farmerWallet: farmer2.publicKey,
          farmerAccount: farmer2Pda,
          pool: poolPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([oracle])
        .rpc();
      assert.fail("Should have thrown QuorumPathRequired");
    } catch (e: any) {
      assert.include(e.message, "QuorumPathRequired");
    }
  });

  describe("M-of-N attestation flow", () => {
    const evalId = evalIdFromString("eval-001");
    let attestationPda: PublicKey;
    const amount = new anchor.BN(2 * LAMPORTS_PER_SOL);
    const score = 82;

    before(async () => {
      await program.methods
        .registerFarmer("KG-ISSYK-KUL")
        .accounts({
          payer: authority.publicKey,
          farmerWallet: farmer3.publicKey,
          farmerAccount: farmer3Pda,
          pool: poolPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .rpc();

      [attestationPda] = PublicKey.findProgramAddressSync(
        [Buffer.from("attestation"), farmer3Pda.toBuffer(), Buffer.from(evalId)],
        program.programId
      );
    });

    it("first oracle attests — quorum not reached", async () => {
      await program.methods
        .attestPayout(evalId, score, amount)
        .accounts({
          oracle: oracle.publicKey,
          farmerWallet: farmer3.publicKey,
          farmerAccount: farmer3Pda,
          pool: poolPda,
          attestation: attestationPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([oracle])
        .rpc();

      const att = await program.account.payoutAttestation.fetch(attestationPda);
      assert.equal(att.attestingCount, 1);
      assert.equal(att.amount.toString(), amount.toString());
      assert.equal(att.aiScore, score);
      assert.isFalse(att.isExecuted);
    });

    it("execute_payout fails before quorum is reached", async () => {
      try {
        await program.methods
          .executePayout(evalId)
          .accounts({
            executor: authority.publicKey,
            farmerWallet: farmer3.publicKey,
            farmerAccount: farmer3Pda,
            pool: poolPda,
            attestation: attestationPda,
          })
          .rpc();
        assert.fail("Should have thrown QuorumNotReached");
      } catch (e: any) {
        assert.include(e.message, "QuorumNotReached");
      }
    });

    it("rejects mismatched attestation values from second oracle", async () => {
      try {
        await program.methods
          .attestPayout(evalId, score, amount.add(new anchor.BN(LAMPORTS_PER_SOL)))
          .accounts({
            oracle: oracle2.publicKey,
            farmerWallet: farmer3.publicKey,
            farmerAccount: farmer3Pda,
            pool: poolPda,
            attestation: attestationPda,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([oracle2])
          .rpc();
        assert.fail("Should have thrown AttestationMismatch");
      } catch (e: any) {
        assert.include(e.message, "AttestationMismatch");
      }
    });

    it("rejects double attestation by same oracle", async () => {
      try {
        await program.methods
          .attestPayout(evalId, score, amount)
          .accounts({
            oracle: oracle.publicKey,
            farmerWallet: farmer3.publicKey,
            farmerAccount: farmer3Pda,
            pool: poolPda,
            attestation: attestationPda,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([oracle])
          .rpc();
        assert.fail("Should have thrown OracleAlreadyAttested");
      } catch (e: any) {
        assert.include(e.message, "OracleAlreadyAttested");
      }
    });

    it("second oracle attests — quorum reached", async () => {
      await program.methods
        .attestPayout(evalId, score, amount)
        .accounts({
          oracle: oracle2.publicKey,
          farmerWallet: farmer3.publicKey,
          farmerAccount: farmer3Pda,
          pool: poolPda,
          attestation: attestationPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([oracle2])
        .rpc();

      const att = await program.account.payoutAttestation.fetch(attestationPda);
      assert.equal(att.attestingCount, 2);
    });

    it("execute_payout succeeds and pays the farmer", async () => {
      const before = await provider.connection.getBalance(farmer3.publicKey);

      await program.methods
        .executePayout(evalId)
        .accounts({
          executor: authority.publicKey,
          farmerWallet: farmer3.publicKey,
          farmerAccount: farmer3Pda,
          pool: poolPda,
          attestation: attestationPda,
        })
        .rpc();

      const after = await provider.connection.getBalance(farmer3.publicKey);
      assert.isTrue(after - before >= amount.toNumber() - 100_000);

      const att = await program.account.payoutAttestation.fetch(attestationPda);
      assert.isTrue(att.isExecuted);

      const farmerAcc = await program.account.farmerAccount.fetch(farmer3Pda);
      assert.deepEqual(farmerAcc.status, { approved: {} });
      assert.equal(farmerAcc.score, score);
    });

    it("execute_payout rejects double execution", async () => {
      try {
        await program.methods
          .executePayout(evalId)
          .accounts({
            executor: authority.publicKey,
            farmerWallet: farmer3.publicKey,
            farmerAccount: farmer3Pda,
            pool: poolPda,
            attestation: attestationPda,
          })
          .rpc();
        assert.fail("Should have thrown AlreadyExecuted");
      } catch (e: any) {
        assert.include(e.message, "AlreadyExecuted");
      }
    });
  });
});
