use anchor_lang::prelude::*;

declare_id!("2tBU1bHZiydZGvcj3Dr5Sj3qQFDbQMrmCkYQt9SXgkfK");

pub const MAX_ORACLES: usize = 5;
pub const EVAL_ID_LEN: usize = 16;
pub const REGION_MAX_LEN: usize = 32;

#[program]
pub mod agri_subsidy {
    use super::*;

    /// Initialise a subsidy pool with parametrised policy and a first oracle.
    /// Quorum is the M in M-of-N: how many distinct oracle attestations are
    /// required before `execute_payout` can move funds.
    pub fn initialize_subsidy_pool(
        ctx: Context<InitializePool>,
        pool_bump: u8,
        min_score: u8,
        max_amount_per_payout: u64,
        quorum: u8,
    ) -> Result<()> {
        require!(min_score <= 100, AgriError::InvalidScore);
        require!(max_amount_per_payout > 0, AgriError::InvalidAmount);
        require!(quorum >= 1, AgriError::InvalidQuorum);

        let pool = &mut ctx.accounts.pool;
        pool.authority = ctx.accounts.authority.key();
        pool.bump = pool_bump;
        pool.total_disbursed = 0;
        pool.farmer_count = 0;
        pool.is_active = true;
        pool.min_score = min_score;
        pool.max_amount_per_payout = max_amount_per_payout;

        pool.oracles = [Pubkey::default(); MAX_ORACLES];
        pool.oracles[0] = ctx.accounts.oracle.key();
        pool.oracle_count = 1;
        pool.quorum = quorum;

        require!(quorum <= pool.oracle_count, AgriError::QuorumExceedsOracleCount);

        emit!(PoolInitialized {
            authority: pool.authority,
            oracle: ctx.accounts.oracle.key(),
            min_score,
            max_amount_per_payout,
            quorum,
        });

        msg!(
            "Pool init. authority={} oracle0={} quorum={}/1 min_score={} max_amount={}",
            pool.authority,
            ctx.accounts.oracle.key(),
            quorum,
            min_score,
            max_amount_per_payout
        );
        Ok(())
    }

    /// Register an additional oracle on a pool. Authority-only.
    /// The first oracle is set during pool init; this adds up to MAX_ORACLES total.
    pub fn register_oracle(ctx: Context<RegisterOracle>) -> Result<()> {
        let pool = &mut ctx.accounts.pool;
        require!(
            pool.authority == ctx.accounts.authority.key(),
            AgriError::UnauthorizedAuthority
        );
        require!(
            (pool.oracle_count as usize) < MAX_ORACLES,
            AgriError::OracleSlotsExhausted
        );

        let new_oracle = ctx.accounts.new_oracle.key();
        for i in 0..(pool.oracle_count as usize) {
            require!(pool.oracles[i] != new_oracle, AgriError::OracleAlreadyRegistered);
        }

        let slot = pool.oracle_count as usize;
        pool.oracles[slot] = new_oracle;
        pool.oracle_count = pool.oracle_count.checked_add(1).unwrap();

        emit!(OracleRegistered {
            pool: pool.key(),
            oracle: new_oracle,
            new_oracle_count: pool.oracle_count,
        });

        msg!("Oracle registered: {} (count={})", new_oracle, pool.oracle_count);
        Ok(())
    }

    /// Adjust the quorum (M in M-of-N). Authority-only.
    /// Quorum must be between 1 and current oracle_count, inclusive.
    pub fn update_quorum(ctx: Context<UpdateQuorum>, new_quorum: u8) -> Result<()> {
        let pool = &mut ctx.accounts.pool;
        require!(
            pool.authority == ctx.accounts.authority.key(),
            AgriError::UnauthorizedAuthority
        );
        require!(new_quorum >= 1, AgriError::InvalidQuorum);
        require!(new_quorum <= pool.oracle_count, AgriError::QuorumExceedsOracleCount);

        let old = pool.quorum;
        pool.quorum = new_quorum;

        emit!(QuorumUpdated {
            pool: pool.key(),
            old_quorum: old,
            new_quorum,
        });

        msg!("Quorum updated {} -> {}/{}", old, new_quorum, pool.oracle_count);
        Ok(())
    }

    /// Register a farmer in the pool.
    pub fn register_farmer(ctx: Context<RegisterFarmer>, region_code: String) -> Result<()> {
        require!(region_code.len() <= REGION_MAX_LEN, AgriError::RegionCodeTooLong);

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.wallet = ctx.accounts.farmer_wallet.key();
        farmer.pool = ctx.accounts.pool.key();
        farmer.region = region_code.clone();
        farmer.status = FarmerStatus::Pending;
        farmer.score = 0;
        farmer.total_received = 0;

        let pool = &mut ctx.accounts.pool;
        pool.farmer_count = pool.farmer_count.checked_add(1).unwrap();

        emit!(FarmerRegistered {
            wallet: farmer.wallet,
            region: region_code,
        });

        msg!("Farmer registered: {}", farmer.wallet);
        Ok(())
    }

    /// Single-oracle payout (legacy / single-quorum path).
    /// Uses the pool's parametrised policy and accepts any registered oracle.
    /// For M-of-N flows, prefer `attest_payout` + `execute_payout`.
    pub fn release_funds_by_oracle(
        ctx: Context<ReleaseFunds>,
        amount: u64,
        ai_score: u8,
    ) -> Result<()> {
        let pool = &ctx.accounts.pool;

        require!(pool.is_active, AgriError::PoolNotActive);
        require!(pool.quorum == 1, AgriError::QuorumPathRequired);
        require!(amount > 0, AgriError::InvalidAmount);
        require!(amount <= pool.max_amount_per_payout, AgriError::AmountTooLarge);
        require!(ai_score >= pool.min_score, AgriError::ScoreBelowThreshold);

        require!(
            is_registered_oracle(pool, &ctx.accounts.oracle.key()),
            AgriError::UnauthorizedOracle
        );

        require!(
            ctx.accounts.farmer_account.status == FarmerStatus::Pending,
            AgriError::AlreadyProcessed
        );

        let new_total = ctx
            .accounts
            .farmer_account
            .total_received
            .checked_add(amount)
            .ok_or(AgriError::AmountTooLarge)?;
        require!(new_total <= pool.max_amount_per_payout, AgriError::AmountTooLarge);

        **ctx.accounts.pool.to_account_info().try_borrow_mut_lamports()? -= amount;
        **ctx.accounts.farmer_wallet.to_account_info().try_borrow_mut_lamports()? += amount;

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.status = FarmerStatus::Approved;
        farmer.score = ai_score;
        farmer.total_received = new_total;

        let pool = &mut ctx.accounts.pool;
        pool.total_disbursed = pool.total_disbursed.checked_add(amount).unwrap();

        emit!(FundsReleased {
            farmer: ctx.accounts.farmer_wallet.key(),
            amount,
            ai_score,
            oracle: ctx.accounts.oracle.key(),
            quorum: 1,
        });

        msg!(
            "Released {} lamports to {} (AI score: {}, single-oracle path)",
            amount,
            ctx.accounts.farmer_wallet.key(),
            ai_score
        );

        Ok(())
    }

    /// Mark a farmer as rejected without payout. Any registered oracle can call.
    pub fn reject_farmer(ctx: Context<RejectFarmer>, ai_score: u8) -> Result<()> {
        require!(
            is_registered_oracle(&ctx.accounts.pool, &ctx.accounts.oracle.key()),
            AgriError::UnauthorizedOracle
        );

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.status = FarmerStatus::Rejected;
        farmer.score = ai_score;

        emit!(FarmerRejected {
            farmer: farmer.wallet,
            ai_score,
        });

        msg!("Farmer {} rejected (score: {})", farmer.wallet, ai_score);
        Ok(())
    }

    /// Submit an attestation toward an M-of-N payout. The first attestation
    /// creates the Attestation PDA and locks (ai_score, amount); subsequent
    /// attestations must match those values exactly. Each oracle can attest
    /// at most once per (farmer, evaluation_id).
    pub fn attest_payout(
        ctx: Context<AttestPayout>,
        evaluation_id: [u8; EVAL_ID_LEN],
        ai_score: u8,
        amount: u64,
    ) -> Result<()> {
        let pool = &ctx.accounts.pool;
        require!(pool.is_active, AgriError::PoolNotActive);
        require!(amount > 0, AgriError::InvalidAmount);
        require!(amount <= pool.max_amount_per_payout, AgriError::AmountTooLarge);
        require!(ai_score >= pool.min_score, AgriError::ScoreBelowThreshold);

        let oracle_key = ctx.accounts.oracle.key();
        require!(
            is_registered_oracle(pool, &oracle_key),
            AgriError::UnauthorizedOracle
        );

        let attestation = &mut ctx.accounts.attestation;
        let initialised = attestation.attesting_count > 0 || attestation.is_executed;

        if !initialised {
            attestation.farmer = ctx.accounts.farmer_account.key();
            attestation.pool = pool.key();
            attestation.evaluation_id = evaluation_id;
            attestation.ai_score = ai_score;
            attestation.amount = amount;
            attestation.attesting_oracles = [Pubkey::default(); MAX_ORACLES];
            attestation.attesting_count = 0;
            attestation.is_executed = false;
        } else {
            require!(attestation.ai_score == ai_score, AgriError::AttestationMismatch);
            require!(attestation.amount == amount, AgriError::AttestationMismatch);
            require!(!attestation.is_executed, AgriError::AlreadyExecuted);
        }

        for i in 0..(attestation.attesting_count as usize) {
            require!(
                attestation.attesting_oracles[i] != oracle_key,
                AgriError::OracleAlreadyAttested
            );
        }

        let slot = attestation.attesting_count as usize;
        require!(slot < MAX_ORACLES, AgriError::OracleSlotsExhausted);
        attestation.attesting_oracles[slot] = oracle_key;
        attestation.attesting_count = attestation.attesting_count.checked_add(1).unwrap();

        emit!(PayoutAttested {
            farmer: attestation.farmer,
            evaluation_id,
            oracle: oracle_key,
            attesting_count: attestation.attesting_count,
            quorum: pool.quorum,
        });

        msg!(
            "Attested by {}: {}/{} (eval={:?})",
            oracle_key,
            attestation.attesting_count,
            pool.quorum,
            &evaluation_id
        );
        Ok(())
    }

    /// Execute the payout once the attestation count reaches pool.quorum.
    /// Anyone (including the farmer) can call this — the contract enforces all checks.
    pub fn execute_payout(
        ctx: Context<ExecutePayout>,
        _evaluation_id: [u8; EVAL_ID_LEN],
    ) -> Result<()> {
        let pool = &ctx.accounts.pool;
        let attestation = &ctx.accounts.attestation;

        require!(pool.is_active, AgriError::PoolNotActive);
        require!(!attestation.is_executed, AgriError::AlreadyExecuted);
        require!(
            attestation.attesting_count >= pool.quorum,
            AgriError::QuorumNotReached
        );
        require!(
            attestation.farmer == ctx.accounts.farmer_account.key(),
            AgriError::AttestationMismatch
        );
        require!(
            ctx.accounts.farmer_account.status == FarmerStatus::Pending,
            AgriError::AlreadyProcessed
        );

        let amount = attestation.amount;
        let new_total = ctx
            .accounts
            .farmer_account
            .total_received
            .checked_add(amount)
            .ok_or(AgriError::AmountTooLarge)?;
        require!(new_total <= pool.max_amount_per_payout, AgriError::AmountTooLarge);

        **ctx.accounts.pool.to_account_info().try_borrow_mut_lamports()? -= amount;
        **ctx.accounts.farmer_wallet.to_account_info().try_borrow_mut_lamports()? += amount;

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.status = FarmerStatus::Approved;
        farmer.score = attestation.ai_score;
        farmer.total_received = new_total;

        let pool = &mut ctx.accounts.pool;
        pool.total_disbursed = pool.total_disbursed.checked_add(amount).unwrap();

        let attestation = &mut ctx.accounts.attestation;
        attestation.is_executed = true;

        emit!(FundsReleased {
            farmer: ctx.accounts.farmer_wallet.key(),
            amount,
            ai_score: attestation.ai_score,
            oracle: attestation.attesting_oracles[0],
            quorum: attestation.attesting_count,
        });

        msg!(
            "Quorum payout executed: {} lamports, {}-of-{}",
            amount,
            attestation.attesting_count,
            pool.oracle_count
        );
        Ok(())
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

fn is_registered_oracle(pool: &SubsidyPool, candidate: &Pubkey) -> bool {
    let n = pool.oracle_count as usize;
    pool.oracles[..n].iter().any(|o| o == candidate)
}

// ─── Account Structs ─────────────────────────────────────────────────────────

#[account]
pub struct SubsidyPool {
    pub authority: Pubkey,
    pub bump: u8,
    pub total_disbursed: u64,
    pub farmer_count: u64,
    pub is_active: bool,
    pub min_score: u8,
    pub max_amount_per_payout: u64,
    pub oracles: [Pubkey; MAX_ORACLES],
    pub oracle_count: u8,
    pub quorum: u8,
}

impl SubsidyPool {
    pub const LEN: usize = 8       // discriminator
        + 32                       // authority
        + 1                        // bump
        + 8                        // total_disbursed
        + 8                        // farmer_count
        + 1                        // is_active
        + 1                        // min_score
        + 8                        // max_amount_per_payout
        + 32 * MAX_ORACLES         // oracles
        + 1                        // oracle_count
        + 1; // quorum
}

#[account]
pub struct FarmerAccount {
    pub wallet: Pubkey,
    pub pool: Pubkey,
    pub region: String,
    pub status: FarmerStatus,
    pub score: u8,
    pub total_received: u64,
}

impl FarmerAccount {
    pub const LEN: usize = 8       // discriminator
        + 32                       // wallet
        + 32                       // pool
        + 4 + REGION_MAX_LEN       // region (length prefix + max chars)
        + 1                        // status
        + 1                        // score
        + 8; // total_received
}

#[account]
pub struct PayoutAttestation {
    pub farmer: Pubkey,
    pub pool: Pubkey,
    pub evaluation_id: [u8; EVAL_ID_LEN],
    pub ai_score: u8,
    pub amount: u64,
    pub attesting_oracles: [Pubkey; MAX_ORACLES],
    pub attesting_count: u8,
    pub is_executed: bool,
}

impl PayoutAttestation {
    pub const LEN: usize = 8       // discriminator
        + 32                       // farmer
        + 32                       // pool
        + EVAL_ID_LEN              // evaluation_id
        + 1                        // ai_score
        + 8                        // amount
        + 32 * MAX_ORACLES         // attesting_oracles
        + 1                        // attesting_count
        + 1; // is_executed
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq)]
pub enum FarmerStatus {
    Pending,
    Approved,
    Rejected,
}

// ─── Instruction Contexts ─────────────────────────────────────────────────────

#[derive(Accounts)]
#[instruction(pool_bump: u8)]
pub struct InitializePool<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,

    /// CHECK: First oracle pubkey provided during init
    pub oracle: AccountInfo<'info>,

    #[account(
        init,
        payer = authority,
        space = SubsidyPool::LEN,
        seeds = [b"subsidy_pool", authority.key().as_ref()],
        bump,
    )]
    pub pool: Account<'info, SubsidyPool>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RegisterOracle<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,

    /// CHECK: Pubkey of the oracle to be added; need not sign
    pub new_oracle: AccountInfo<'info>,

    #[account(
        mut,
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,
}

#[derive(Accounts)]
pub struct UpdateQuorum<'info> {
    pub authority: Signer<'info>,

    #[account(
        mut,
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,
}

#[derive(Accounts)]
pub struct RegisterFarmer<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    /// CHECK: The farmer's wallet address
    pub farmer_wallet: AccountInfo<'info>,

    #[account(
        init,
        payer = payer,
        space = FarmerAccount::LEN,
        seeds = [b"farmer", pool.key().as_ref(), farmer_wallet.key().as_ref()],
        bump,
    )]
    pub farmer_account: Account<'info, FarmerAccount>,

    #[account(mut)]
    pub pool: Account<'info, SubsidyPool>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ReleaseFunds<'info> {
    pub oracle: Signer<'info>,

    /// CHECK: Farmer wallet receives the SOL
    #[account(mut)]
    pub farmer_wallet: AccountInfo<'info>,

    #[account(
        mut,
        seeds = [b"farmer", pool.key().as_ref(), farmer_wallet.key().as_ref()],
        bump,
        constraint = farmer_account.wallet == farmer_wallet.key() @ AgriError::WalletMismatch,
    )]
    pub farmer_account: Account<'info, FarmerAccount>,

    #[account(
        mut,
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RejectFarmer<'info> {
    pub oracle: Signer<'info>,

    /// CHECK: Farmer wallet reference
    pub farmer_wallet: AccountInfo<'info>,

    #[account(
        mut,
        seeds = [b"farmer", pool.key().as_ref(), farmer_wallet.key().as_ref()],
        bump,
        constraint = farmer_account.wallet == farmer_wallet.key() @ AgriError::WalletMismatch,
    )]
    pub farmer_account: Account<'info, FarmerAccount>,

    #[account(
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,
}

#[derive(Accounts)]
#[instruction(evaluation_id: [u8; EVAL_ID_LEN])]
pub struct AttestPayout<'info> {
    #[account(mut)]
    pub oracle: Signer<'info>,

    /// CHECK: Farmer wallet reference; must match farmer_account
    pub farmer_wallet: AccountInfo<'info>,

    #[account(
        seeds = [b"farmer", pool.key().as_ref(), farmer_wallet.key().as_ref()],
        bump,
        constraint = farmer_account.wallet == farmer_wallet.key() @ AgriError::WalletMismatch,
    )]
    pub farmer_account: Account<'info, FarmerAccount>,

    #[account(
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,

    #[account(
        init_if_needed,
        payer = oracle,
        space = PayoutAttestation::LEN,
        seeds = [b"attestation", farmer_account.key().as_ref(), evaluation_id.as_ref()],
        bump,
    )]
    pub attestation: Account<'info, PayoutAttestation>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(evaluation_id: [u8; EVAL_ID_LEN])]
pub struct ExecutePayout<'info> {
    #[account(mut)]
    pub executor: Signer<'info>,

    /// CHECK: Farmer wallet receives the SOL
    #[account(mut)]
    pub farmer_wallet: AccountInfo<'info>,

    #[account(
        mut,
        seeds = [b"farmer", pool.key().as_ref(), farmer_wallet.key().as_ref()],
        bump,
        constraint = farmer_account.wallet == farmer_wallet.key() @ AgriError::WalletMismatch,
    )]
    pub farmer_account: Account<'info, FarmerAccount>,

    #[account(
        mut,
        seeds = [b"subsidy_pool", pool.authority.as_ref()],
        bump = pool.bump,
    )]
    pub pool: Account<'info, SubsidyPool>,

    #[account(
        mut,
        seeds = [b"attestation", farmer_account.key().as_ref(), evaluation_id.as_ref()],
        bump,
    )]
    pub attestation: Account<'info, PayoutAttestation>,

    pub system_program: Program<'info, System>,
}

// ─── Events ───────────────────────────────────────────────────────────────────

#[event]
pub struct PoolInitialized {
    pub authority: Pubkey,
    pub oracle: Pubkey,
    pub min_score: u8,
    pub max_amount_per_payout: u64,
    pub quorum: u8,
}

#[event]
pub struct OracleRegistered {
    pub pool: Pubkey,
    pub oracle: Pubkey,
    pub new_oracle_count: u8,
}

#[event]
pub struct QuorumUpdated {
    pub pool: Pubkey,
    pub old_quorum: u8,
    pub new_quorum: u8,
}

#[event]
pub struct FarmerRegistered {
    pub wallet: Pubkey,
    pub region: String,
}

#[event]
pub struct PayoutAttested {
    pub farmer: Pubkey,
    pub evaluation_id: [u8; EVAL_ID_LEN],
    pub oracle: Pubkey,
    pub attesting_count: u8,
    pub quorum: u8,
}

#[event]
pub struct FundsReleased {
    pub farmer: Pubkey,
    pub amount: u64,
    pub ai_score: u8,
    pub oracle: Pubkey,
    pub quorum: u8,
}

#[event]
pub struct FarmerRejected {
    pub farmer: Pubkey,
    pub ai_score: u8,
}

// ─── Errors ───────────────────────────────────────────────────────────────────

#[error_code]
pub enum AgriError {
    #[msg("AI score is below the pool's minimum threshold")]
    ScoreBelowThreshold,

    #[msg("Score must be between 0 and 100 inclusive")]
    InvalidScore,

    #[msg("Unauthorized oracle — caller is not registered on this pool")]
    UnauthorizedOracle,

    #[msg("Caller is not the pool authority")]
    UnauthorizedAuthority,

    #[msg("Amount must be greater than 0")]
    InvalidAmount,

    #[msg("Amount exceeds the pool's max_amount_per_payout")]
    AmountTooLarge,

    #[msg("Pool is not active")]
    PoolNotActive,

    #[msg("Farmer wallet does not match account")]
    WalletMismatch,

    #[msg("Region code must be 32 characters or less")]
    RegionCodeTooLong,

    #[msg("Farmer has already been processed (approved or rejected)")]
    AlreadyProcessed,

    #[msg("Quorum must be at least 1")]
    InvalidQuorum,

    #[msg("Quorum cannot exceed the number of registered oracles")]
    QuorumExceedsOracleCount,

    #[msg("No more oracle slots available on this pool")]
    OracleSlotsExhausted,

    #[msg("Oracle is already registered on this pool")]
    OracleAlreadyRegistered,

    #[msg("Use attest_payout + execute_payout when quorum > 1")]
    QuorumPathRequired,

    #[msg("Attestation values do not match the existing attestation")]
    AttestationMismatch,

    #[msg("Oracle has already attested this evaluation")]
    OracleAlreadyAttested,

    #[msg("Quorum not yet reached for this evaluation")]
    QuorumNotReached,

    #[msg("Attestation has already been executed")]
    AlreadyExecuted,
}
