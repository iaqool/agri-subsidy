import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { AgriSubsidy } from "../target/types/agri_subsidy";
import { PublicKey, Keypair, LAMPORTS_PER_SOL } from "@solana/web3.js";
import { assert } from "chai";

describe("agri_subsidy", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.AgriSubsidy as Program<AgriSubsidy>;
  const authority = provider.wallet as anchor.Wallet;

  // Oracle keypair (наш Python-агент)
  const oracle = Keypair.generate();

  // Demo farmer keypair
  const farmer = Keypair.generate();

  let poolPda: PublicKey;
  let poolBump: number;
  let farmerAccountPda: PublicKey;

  before(async () => {
    // Derive Pool PDA
    [poolPda, poolBump] = PublicKey.findProgramAddressSync(
      [Buffer.from("subsidy_pool"), authority.publicKey.toBuffer()],
      program.programId
    );

    // Derive Farmer Account PDA
    [farmerAccountPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("farmer"), poolPda.toBuffer(), farmer.publicKey.toBuffer()],
      program.programId
    );

    // Airdrop to oracle and farmer for fees
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(oracle.publicKey, 2 * LAMPORTS_PER_SOL)
    );
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(farmer.publicKey, 0.1 * LAMPORTS_PER_SOL)
    );
  });

  it("✅ initializes the subsidy pool", async () => {
    await program.methods
      .initializeSubsidyPool(poolBump)
      .accounts({
        authority: authority.publicKey,
        oracle: oracle.publicKey,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    const pool = await program.account.subsidyPool.fetch(poolPda);
    assert.equal(pool.authority.toString(), authority.publicKey.toString());
    assert.equal(pool.oracle.toString(), oracle.publicKey.toString());
    assert.equal(pool.farmerCount.toNumber(), 0);
    assert.isTrue(pool.isActive);

    console.log("Pool initialized at:", poolPda.toString());
  });

  it("✅ registers a farmer", async () => {
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
    assert.equal(farmerAcc.wallet.toString(), farmer.publicKey.toString());
    assert.equal(farmerAcc.region, "UA-ZAPORIZHZHIA");
    assert.deepEqual(farmerAcc.status, { pending: {} });

    console.log("Farmer registered:", farmer.publicKey.toString());
  });

  it("✅ releases funds by oracle when score >= 55", async () => {
    // Fund the pool PDA
    const fundTx = await provider.connection.requestAirdrop(poolPda, 3 * LAMPORTS_PER_SOL);
    await provider.connection.confirmTransaction(fundTx);

    const farmerBalanceBefore = await provider.connection.getBalance(farmer.publicKey);
    const amount = new anchor.BN(1.5 * LAMPORTS_PER_SOL);
    const aiScore = 78;

    await program.methods
      .releaseFundsByOracle(amount, aiScore)
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
    assert.equal(farmerAcc.score, aiScore);

    const farmerBalanceAfter = await provider.connection.getBalance(farmer.publicKey);
    assert.isTrue(farmerBalanceAfter > farmerBalanceBefore);

    console.log(`Released ${amount.toNumber() / LAMPORTS_PER_SOL} SOL to farmer`);
    console.log(`Farmer balance: ${farmerBalanceAfter / LAMPORTS_PER_SOL} SOL`);
  });

  it("❌ rejects release when score < 55", async () => {
    // Register a second farmer
    const farmer2 = Keypair.generate();
    const [farmer2Pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("farmer"), poolPda.toBuffer(), farmer2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerFarmer("EG-NILE-DELTA")
      .accounts({
        payer: authority.publicKey,
        farmerWallet: farmer2.publicKey,
        farmerAccount: farmer2Pda,
        pool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    // Try to release with score 40 (below threshold)
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
      assert.fail("Should have thrown ScoreBelowThreshold error");
    } catch (e: any) {
      assert.include(e.message, "ScoreBelowThreshold");
      console.log("✅ Correctly rejected: score 40 < threshold 55");
    }
  });

  it("❌ rejects unauthorized oracle", async () => {
    const fakeOracle = Keypair.generate();

    try {
      await program.methods
        .releaseFundsByOracle(new anchor.BN(1 * LAMPORTS_PER_SOL), 90)
        .accounts({
          oracle: fakeOracle.publicKey,
          farmerWallet: farmer.publicKey,
          farmerAccount: farmerAccountPda,
          pool: poolPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([fakeOracle])
        .rpc();
      assert.fail("Should have thrown UnauthorizedOracle error");
    } catch (e: any) {
      assert.include(e.message, "UnauthorizedOracle");
      console.log("✅ Correctly rejected unauthorized oracle");
    }
  });

  it("📊 verifies pool stats after operations", async () => {
    const pool = await program.account.subsidyPool.fetch(poolPda);
    console.log("Total disbursed:", pool.totalDisbursed.toNumber() / LAMPORTS_PER_SOL, "SOL");
    console.log("Farmer count:", pool.farmerCount.toNumber());
    assert.isTrue(pool.totalDisbursed.toNumber() > 0);
    assert.equal(pool.farmerCount.toNumber(), 2);
  });
});
