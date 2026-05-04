use anchor_lang::prelude::*;

declare_id!("971ZxLBhqc9p7rqCX5UkpknEo4AJUfG15UqT99GZbXpB");

#[program]
pub mod agri_subsidy {
    use super::*;

    /// Инициализация пула субсидий.
    /// Создаёт PDA-эскроу и привязывает его к Authority.
    pub fn initialize_subsidy_pool(
        ctx: Context<InitializePool>,
        pool_bump: u8,
    ) -> Result<()> {
        let pool = &mut ctx.accounts.pool;
        pool.authority = ctx.accounts.authority.key();
        pool.oracle    = ctx.accounts.oracle.key();
        pool.bump      = pool_bump;
        pool.total_disbursed = 0;
        pool.farmer_count    = 0;
        pool.is_active       = true;

        emit!(PoolInitialized {
            authority: pool.authority,
            oracle: pool.oracle,
        });

        msg!("AgriSubsidy pool initialized. Authority: {}", pool.authority);
        Ok(())
    }

    /// Регистрация фермера в системе.
    pub fn register_farmer(
        ctx: Context<RegisterFarmer>,
        region_code: String,
    ) -> Result<()> {
        require!(region_code.len() <= 32, AgriError::RegionCodeTooLong);

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.wallet  = ctx.accounts.farmer_wallet.key();
        farmer.pool    = ctx.accounts.pool.key();
        farmer.region  = region_code.clone();
        farmer.status  = FarmerStatus::Pending;
        farmer.score   = 0;
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

    /// Выплата субсидии фермеру (вызывается Oracle).
    /// Только Oracle-ключ (наш Python-агент) может вызвать эту инструкцию.
    pub fn release_funds_by_oracle(
        ctx: Context<ReleaseFunds>,
        amount: u64,
        ai_score: u8,
    ) -> Result<()> {
        require!(ai_score >= 55, AgriError::ScoreBelowThreshold);
        require!(amount > 0, AgriError::InvalidAmount);
        require!(amount <= 5_000_000_000, AgriError::AmountTooLarge); // max 5 SOL
        require!(ctx.accounts.pool.is_active, AgriError::PoolNotActive);

        require!(
            ctx.accounts.pool.oracle == ctx.accounts.oracle.key(),
            AgriError::UnauthorizedOracle
        );

        // Prevent double payout — farmer must be in Pending status
        require!(
            ctx.accounts.farmer_account.status == FarmerStatus::Pending,
            AgriError::AlreadyProcessed
        );

        // Enforce per-farmer cumulative cap (5 SOL)
        let new_total = ctx.accounts.farmer_account.total_received
            .checked_add(amount)
            .ok_or(AgriError::AmountTooLarge)?;
        require!(new_total <= 5_000_000_000, AgriError::AmountTooLarge);

        // Трансфер SOL из pool-PDA → кошелёк фермера
        let pool = &ctx.accounts.pool;
        let pool_seeds = &[
            b"subsidy_pool".as_ref(),
            pool.authority.as_ref(),
            &[pool.bump],
        ];
        let _signer_seeds = &[&pool_seeds[..]];

        **ctx.accounts.pool.to_account_info().try_borrow_mut_lamports()? -= amount;
        **ctx.accounts.farmer_wallet.to_account_info().try_borrow_mut_lamports()? += amount;

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.status = FarmerStatus::Approved;
        farmer.score  = ai_score;
        farmer.total_received = new_total;

        // Обновляем пул
        let pool = &mut ctx.accounts.pool;
        pool.total_disbursed = pool.total_disbursed.checked_add(amount).unwrap();

        emit!(FundsReleased {
            farmer:   ctx.accounts.farmer_wallet.key(),
            amount,
            ai_score,
            oracle:   ctx.accounts.oracle.key(),
        });

        msg!(
            "Released {} lamports to {} (AI score: {})",
            amount,
            ctx.accounts.farmer_wallet.key(),
            ai_score
        );

        Ok(())
    }

    /// Отклонение заявки (помечаем фермера как Rejected без выплаты).
    pub fn reject_farmer(
        ctx: Context<RejectFarmer>,
        ai_score: u8,
    ) -> Result<()> {
        require!(
            ctx.accounts.pool.oracle == ctx.accounts.oracle.key(),
            AgriError::UnauthorizedOracle
        );

        let farmer = &mut ctx.accounts.farmer_account;
        farmer.status = FarmerStatus::Rejected;
        farmer.score  = ai_score;

        emit!(FarmerRejected {
            farmer: farmer.wallet,
            ai_score,
        });

        msg!("Farmer {} rejected (score: {})", farmer.wallet, ai_score);
        Ok(())
    }
}

// ─── Account Structs ─────────────────────────────────────────────────────────

#[account]
pub struct SubsidyPool {
    pub authority:        Pubkey,  // Admin who created the pool
    pub oracle:           Pubkey,  // AI Oracle pubkey (our Python agent)
    pub bump:             u8,      // PDA bump
    pub total_disbursed:  u64,     // Total lamports sent out
    pub farmer_count:     u64,     // Number of registered farmers
    pub is_active:        bool,    // Pool active flag
}

impl SubsidyPool {
    pub const LEN: usize = 8       // discriminator
        + 32   // authority
        + 32   // oracle
        + 1    // bump
        + 8    // total_disbursed
        + 8    // farmer_count
        + 1;   // is_active
}

#[account]
pub struct FarmerAccount {
    pub wallet:         Pubkey,
    pub pool:           Pubkey,
    pub region:         String,   // up to 32 chars
    pub status:         FarmerStatus,
    pub score:          u8,
    pub total_received: u64,
}

impl FarmerAccount {
    pub const LEN: usize = 8       // discriminator
        + 32   // wallet
        + 32   // pool
        + 4 + 32  // region string (length prefix + max 32 chars)
        + 1    // status enum
        + 1    // score
        + 8;   // total_received
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

    /// CHECK: Oracle public key provided during init
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
    /// The Oracle (must match pool.oracle)
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

// ─── Events ───────────────────────────────────────────────────────────────────

#[event]
pub struct PoolInitialized {
    pub authority: Pubkey,
    pub oracle:    Pubkey,
}

#[event]
pub struct FarmerRegistered {
    pub wallet: Pubkey,
    pub region: String,
}

#[event]
pub struct FundsReleased {
    pub farmer:   Pubkey,
    pub amount:   u64,
    pub ai_score: u8,
    pub oracle:   Pubkey,
}

#[event]
pub struct FarmerRejected {
    pub farmer:   Pubkey,
    pub ai_score: u8,
}

// ─── Errors ───────────────────────────────────────────────────────────────────

#[error_code]
pub enum AgriError {
    #[msg("AI score is below approval threshold (55)")]
    ScoreBelowThreshold,

    #[msg("Unauthorized oracle — only registered oracle can release funds")]
    UnauthorizedOracle,

    #[msg("Amount must be greater than 0")]
    InvalidAmount,

    #[msg("Amount exceeds maximum per farmer (5 SOL)")]
    AmountTooLarge,

    #[msg("Pool is not active")]
    PoolNotActive,

    #[msg("Farmer wallet does not match account")]
    WalletMismatch,

    #[msg("Region code must be 32 characters or less")]
    RegionCodeTooLong,

    #[msg("Farmer has already been processed (approved or rejected)")]
    AlreadyProcessed,
}
