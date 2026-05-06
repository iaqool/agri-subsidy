import { useEffect, useRef } from 'react';
import './landing.css';

const GITHUB_URL = 'https://github.com/iaqool/agri-subsidy';

const logos = [
  'Solana',
  'Anchor',
  'OpenAI',
  'Sentinel NDVI',
  'Copernicus',
  'NASA MODIS',
  'OpenWeatherMap',
  'Helius',
];

const localizedCopy = {
  ru: {
    readDocs: 'Документация',
    launchApp: 'Открыть дашборд',
    heroLive: 'LIVE ON DEVNET',
    heroBadge: 'Drought-specific oracle layer для Solana →',
    heroTitleTop: 'Спутник видит засуху —',
    heroTitleBottom: 'смарт-контракт платит фермеру.',
    heroSub:
      'Drought-specific oracle для параметрических страховых протоколов и государственных программ помощи фермерам. NDVI и климат превращаются в верифицируемые ончейн-триггеры выплат на Solana.',
    heroStats: ['FINALIZED TX', 'NDVI РАЗРЕШЕНИЕ', 'ОНЧЕЙН-КОНТРОЛЬ', 'ОРАКУЛ-КВОРУМ'],
    infraLabel: 'Инфраструктурный стек',
    capabilitiesKicker: 'Возможности',
    capabilitiesTitle: 'AI + спутники + Anchor-контракт',
    capabilitiesDescription:
      'Композитный drought-score объясним, oracle-уровень — отдельный от приложения. Парам-страх протоколы могут подписаться на feed как на Pyth, только для drought-событий.',
    featureCards: [
      {
        title: 'NDVI + климат',
        body: 'Sentinel и MODIS дают вегетационный индекс, OpenWeatherMap — климат. Композитный score с весами 0.4 / 0.4 / 0.2.',
        status: 'Sentinel + MODIS',
      },
      {
        title: 'Объяснимый AI-score',
        body: 'OpenAI стримит логику оценки в SSE, fallback-агент работает без AI. Каждый score — с разбором по компонентам.',
        status: 'GPT-4o · fallback ready',
      },
      {
        title: 'Dual-Validation в Anchor',
        body: 'AI рекомендует офчейн. Anchor проверяет порог ≥ 55, лимит ≤ 5 SOL, авторизованного оракула. Кворум M-of-N — в roadmap.',
        status: 'Devnet live',
      },
    ],
    integrationsTitle: 'Компонентные интеграции',
    integrationsDescription:
      'Слой данных, скоринга и enforcement — каждый модуль заменяем. NDVI-провайдеры, AI-движки и oracle-кворум подключаются по интерфейсу.',
    howItWorksKicker: 'Как это работает',
    howItWorksTitle: 'От NDVI-сигнала до ончейн-выплаты',
    steps: [
      {
        title: '1. Сбор данных',
        body: 'Sentinel и MODIS NDVI плюс OpenWeatherMap нормализуются по координатам региона.',
      },
      {
        title: '2. AI-скоринг',
        body: 'OpenAI с fallback-агентом формирует объяснимый drought-score 0–100.',
      },
      {
        title: '3. Anchor enforcement',
        body: 'Контракт проверяет порог, лимиты и авторизованного оракула. Final commitment.',
      },
      {
        title: '4. Выплата за минуты',
        body: 'SOL уходит на кошелёк фермера с полным ончейн аудит-трейлом.',
      },
    ],
    liveOracleTitle: 'Пульс оракула',
    liveOracleDescription: 'Таймлайн Dual-Validation и тренд пропускной способности.',
    minEvalLabel: 'мин оценка',
    policyPassLabel: 'прохождение policy %',
    problemVisionKicker: 'Проблема и решение',
    problemVisionTitle: 'Чиним рельсы выплат для climate-shocks',
    problemKicker: 'Проблема',
    problemText:
      'Засуха в 2024 году принесла $40B+ убытков агросектору. 70% мелких фермеров мира не имеют доступа к страховке. Ручные клеймы — 30–90 дней. Гос-субсидии теряют 15–40% на коррупции.',
    solutionKicker: 'Решение',
    solutionText:
      'Drought oracle layer на Solana. Парам-страх протоколы (AMOCA-like), перестраховщики и гос-программы подключаются к одному feed и одной Anchor-rail. Тригерр верифицируем, выплата за минуты, аудит-трейл навсегда.',
    customerKicker: 'Кому это нужно',
    customerTitle: 'Три ICP, один oracle',
    customerCards: [
      {
        title: 'Парам-страх протоколы',
        body: 'AMOCA, SeedFlow, NOVA и аналоги — стрим drought-триггеров в их смарт-контракты. $0.50 за вызов, инфра не на них.',
        status: 'основной фокус',
      },
      {
        title: 'Перестраховщики',
        body: 'Munich Re, Swiss Re sandbox-программы — white-label oracle для портфелей в развивающихся рынках. Каждая выплата трассируема.',
        status: 'B2B traditional',
      },
      {
        title: 'Гос-программы помощи',
        body: 'Минсельхозы и доноры — замена ручной выдачи на автоматические аудитуемые рельсы. Пилоты в Центральной Азии.',
        status: 'Q3 2026 пилот',
      },
    ],
    roadmapKicker: 'Roadmap',
    roadmapTitle: 'Что сделано и что дальше',
    roadmapItems: [
      { tag: 'Q4 2025', text: 'Anchor-программа на Devnet, dual-validation архитектура', done: true },
      { tag: 'Q4 2025', text: 'AI-оракул MVP с fallback-агентом и SSE стримингом', done: true },
      { tag: 'Q1 2026', text: 'Сабмит на Colosseum Frontier — DePIN, Climate, Public Goods', done: true },
      { tag: 'Q2 2026', text: 'Multi-oracle кворум M-of-N, параметризуемые policy terms', done: false },
      { tag: 'Q2 2026', text: 'Первая интеграция с парам-страх протоколом', done: false },
      { tag: 'Q3 2026', text: 'Реальный Sentinel/MODIS NDVI, mainnet beta', done: false },
      { tag: 'Q3 2026', text: 'Public-benefit пилот с минсельхозом одной страны', done: false },
      { tag: 'Q4 2026', text: 'Production launch, $1M+ TVL в страховых пулах', done: false },
    ],
    ctaTitle: 'Быстрая помощь, усиленная политикой.',
    ctaDescription:
      'Откройте дашборд, чтобы запустить AI-оценку и проверить ончейн-предохранители.',
  },
  en: {
    readDocs: 'Read Docs',
    launchApp: 'Launch App',
    heroLive: 'LIVE ON DEVNET',
    heroBadge: 'Drought-specific oracle layer for Solana →',
    heroTitleTop: 'Satellites see drought.',
    heroTitleBottom: 'Smart contracts pay farmers.',
    heroSub:
      'A drought-specific oracle for parametric insurance protocols and public farmer relief programs. We turn NDVI and climate signals into verifiable on-chain payout triggers on Solana.',
    heroStats: ['FINALIZED TX', 'NDVI RESOLUTION', 'ON-CHAIN ENFORCEMENT', 'ORACLE QUORUM'],
    infraLabel: 'Infrastructure stack',
    capabilitiesKicker: 'Capabilities',
    capabilitiesTitle: 'AI + Satellite + Anchor',
    capabilitiesDescription:
      'Explainable composite drought score. Oracle layer separated from application. Parametric protocols subscribe to the feed the same way DeFi protocols subscribe to Pyth — but for drought events.',
    featureCards: [
      {
        title: 'NDVI + Climate',
        body: 'Sentinel and MODIS for vegetation index, OpenWeatherMap for climate. Weighted composite (0.4 / 0.4 / 0.2).',
        status: 'Sentinel + MODIS',
      },
      {
        title: 'Explainable AI Score',
        body: 'OpenAI streams reasoning over SSE; rule-based fallback runs when GPT-4o is unavailable. Every score includes a per-component breakdown.',
        status: 'GPT-4o · fallback ready',
      },
      {
        title: 'Dual-Validation in Anchor',
        body: 'AI recommends off-chain. Anchor enforces score ≥ 55, ≤ 5 SOL cap, authorized oracle. M-of-N quorum on the roadmap.',
        status: 'Devnet live',
      },
    ],
    integrationsTitle: 'Composable Integrations',
    integrationsDescription:
      'Each layer — data, scoring, enforcement — is swappable. NDVI providers, AI engines, and oracle quorum members plug in via clear interfaces.',
    howItWorksKicker: 'How it works',
    howItWorksTitle: 'From NDVI signal to on-chain payout',
    steps: [
      {
        title: '1. Ingest data',
        body: 'Sentinel and MODIS NDVI plus OpenWeatherMap, normalized by region coordinates.',
      },
      {
        title: '2. AI scoring',
        body: 'OpenAI with rule-based fallback produces an explainable drought score from 0 to 100.',
      },
      {
        title: '3. Anchor enforcement',
        body: 'The contract checks threshold, caps, and authorized oracle. Finalized commitment, no rollback.',
      },
      {
        title: '4. Payout in minutes',
        body: 'SOL lands in the farmer wallet with a full on-chain audit trail.',
      },
    ],
    liveOracleTitle: 'Live Oracle Pulse',
    liveOracleDescription: 'Dual-Validation timeline and throughput trend.',
    minEvalLabel: 'min eval',
    policyPassLabel: 'policy pass %',
    problemVisionKicker: 'Problem & Solution',
    problemVisionTitle: 'Fixing the payout rails for climate shocks',
    problemKicker: 'The Problem',
    problemText:
      'Drought caused over $40B in agricultural losses in 2024. 70% of smallholder farmers globally have no insurance access. Manual claims take 30–90 days. Public subsidy programs leak 15–40% to corruption.',
    solutionKicker: 'The Solution',
    solutionText:
      'A drought oracle layer on Solana. Parametric protocols (AMOCA-like), reinsurers, and public relief programs plug into one feed and one Anchor-enforced payout rail. Verifiable trigger, minutes not months, audit trail forever.',
    customerKicker: 'Who it is for',
    customerTitle: 'Three ICPs, one oracle',
    customerCards: [
      {
        title: 'Parametric protocols',
        body: 'AMOCA, SeedFlow, NOVA and the like — stream drought triggers into their smart contracts. $0.50 per evaluation, no infra to maintain.',
        status: 'primary focus',
      },
      {
        title: 'Reinsurers',
        body: 'Munich Re and Swiss Re sandbox programs — white-label drought oracle for emerging-market portfolios. Every payout traceable on-chain.',
        status: 'B2B traditional',
      },
      {
        title: 'Public relief programs',
        body: 'Ministries of agriculture and donor agencies — replace manual disbursement with automated, auditable rails. Pilots in Central Asia.',
        status: 'Q3 2026 pilot',
      },
    ],
    roadmapKicker: 'Roadmap',
    roadmapTitle: 'Done and next',
    roadmapItems: [
      { tag: 'Q4 2025', text: 'Anchor program live on Devnet, dual-validation architecture', done: true },
      { tag: 'Q4 2025', text: 'AI oracle MVP with fallback agent and SSE streaming', done: true },
      { tag: 'Q1 2026', text: 'Colosseum Frontier submission — DePIN, Climate, Public Goods', done: true },
      { tag: 'Q2 2026', text: 'Multi-oracle M-of-N quorum, parameterized policy terms', done: false },
      { tag: 'Q2 2026', text: 'First parametric-protocol integration', done: false },
      { tag: 'Q3 2026', text: 'Real Sentinel/MODIS NDVI ingestion, mainnet beta', done: false },
      { tag: 'Q3 2026', text: 'Public-benefit pilot with one Central-Asian Ministry of Agriculture', done: false },
      { tag: 'Q4 2026', text: 'Production launch, $1M+ TVL in subsidy pools', done: false },
    ],
    ctaTitle: 'Fast payouts, enforced by policy.',
    ctaDescription:
      'Open the dashboard to run an AI evaluation and verify on-chain safety checks.',
  },
};

export default function Landing({ onLaunch, language = 'ru', onLanguageChange = () => {} }) {
  const rootRef = useRef(null);
  const t = localizedCopy[language] ?? localizedCopy.ru;

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    const cleanups = [];

    const footerYear = root.querySelector('#footerYear');
    if (footerYear) footerYear.textContent = String(new Date().getFullYear());

    const nav = root.querySelector('#landing-nav');
    const onScroll = () => {
      if (nav) nav.classList.toggle('scrolled', window.scrollY > 60);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    cleanups.push(() => window.removeEventListener('scroll', onScroll));

    // noise texture
    {
      const size = 96;
      const canvas = document.createElement('canvas');
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        const image = ctx.createImageData(size, size);
        for (let i = 0; i < image.data.length; i += 4) {
          const v = (Math.random() * 255) | 0;
          image.data[i] = v;
          image.data[i + 1] = v;
          image.data[i + 2] = v;
          image.data[i + 3] = 100;
        }
        ctx.putImageData(image, 0, 0);
        root.style.setProperty('--landing-noise-url', `url(${canvas.toDataURL('image/png')})`);
      }
    }

    // reveal
    {
      const revealObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add('visible');
              revealObserver.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.16, rootMargin: '0px 0px -30px 0px' },
      );
      root.querySelectorAll('.reveal,.stagger').forEach((el) => revealObserver.observe(el));
      cleanups.push(() => revealObserver.disconnect());
    }

    // counter animation
    {
      const animateCounter = (el, target, duration) => {
        let startTime = null;
        const isFloat = String(target).includes('.');
        const step = (ts) => {
          if (startTime === null) startTime = ts;
          const p = Math.min((ts - startTime) / duration, 1);
          const ease = 1 - Math.pow(1 - p, 3);
          const val = target * ease;
          el.textContent = isFloat ? val.toFixed(2) : String(Math.floor(val));
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      };

      const counterObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              const t = parseFloat(entry.target.getAttribute('data-count') ?? '0');
              animateCounter(entry.target, t, 1500);
              counterObserver.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.45 },
      );
      root.querySelectorAll('[data-count]').forEach((el) => counterObserver.observe(el));
      cleanups.push(() => counterObserver.disconnect());
    }

    // integration badges
    {
      const node = root.querySelector('#integrationBadges');
      if (node) {
        node.innerHTML = '';
        [
          'Sentinel-2',
          'OpenAI',
          'Anchor',
          'Solana Devnet',
          'Helius',
          'Pyth',
          'IPFS',
          'OpenTelemetry',
        ].forEach((name) => {
          const badge = document.createElement('span');
          badge.className = 'integration-badge';
          badge.textContent = name;
          node.appendChild(badge);
        });
      }
    }

    // waveform bars
    {
      const waveform = root.querySelector('#waveform');
      if (waveform) {
        waveform.innerHTML = '';
        const heights = [30, 56, 82, 44, 71, 58, 88, 49, 77, 40, 68, 54];
        heights.forEach((h, i) => {
          const bar = document.createElement('span');
          bar.className = 'wave-bar';
          bar.style.height = `${h}%`;
          bar.style.animationDelay = `${i * 0.08}s`;
          waveform.appendChild(bar);
        });
      }
    }

    // dashboard bars
    {
      const dashBars = root.querySelector('#dashBars');
      if (dashBars) {
        dashBars.innerHTML = '';
        const heights = [45, 62, 78, 55, 82, 70, 90, 65, 75, 50, 88, 60];
        heights.forEach((h, i) => {
          const bar = document.createElement('span');
          bar.style.height = `${h}%`;
          bar.style.animationDelay = `${i * 0.04}s`;
          dashBars.appendChild(bar);
        });
      }
    }

    // sparkline bars
    {
      const sparkData = {
        spark1: [12, 25, 20, 34, 40, 38, 47, 54, 52, 63],
        spark2: [64, 58, 49, 43, 38, 33, 28, 25, 21, 18],
      };
      Object.entries(sparkData).forEach(([id, data]) => {
        const el = root.querySelector(`#${id}`);
        if (!el) return;
        el.innerHTML = '';
        const max = Math.max(...data);
        data.forEach((v, i) => {
          const b = document.createElement('span');
          b.className = 'spark-bar';
          b.style.height = `${(v / max) * 100}%`;
          b.style.animationDelay = `${i * 0.05}s`;
          el.appendChild(b);
        });
      });
    }

    // particles
    {
      const createParticles = (id, count) => {
        const host = root.querySelector(`#${id}`);
        if (!host) return;
        host.innerHTML = '';
        for (let i = 0; i < count; i += 1) {
          const p = document.createElement('span');
          p.className = 'particle';
          p.style.left = `${Math.random() * 100}%`;
          p.style.top = `${60 + Math.random() * 35}%`;
          p.style.animationDelay = `${Math.random() * 6}s`;
          p.style.animationDuration = `${6 + Math.random() * 10}s`;
          host.appendChild(p);
        }
      };
      createParticles('featureParticles', 18);
      createParticles('ctaParticles', 14);
    }

    // card tilt
    root.querySelectorAll('.tilt-card').forEach((card) => {
      const onMove = (event) => {
        const r = card.getBoundingClientRect();
        const x = (event.clientX - r.left) / r.width - 0.5;
        const y = (event.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(760px) rotateX(${(-y * 5).toFixed(
          2,
        )}deg) rotateY(${(x * 5).toFixed(2)}deg)`;
      };
      const onLeave = () => {
        card.style.transform = '';
      };
      card.addEventListener('mousemove', onMove);
      card.addEventListener('mouseleave', onLeave);
      cleanups.push(() => {
        card.removeEventListener('mousemove', onMove);
        card.removeEventListener('mouseleave', onLeave);
      });
    });

    // Unicorn Studio loader (safe, optional)
    {
      const usNode = root.querySelector('[data-us-project]');
      if (usNode) {
        const init = () => {
          if (window.UnicornStudio && typeof window.UnicornStudio.init === 'function') {
            window.UnicornStudio.init();
          }
        };
        if (window.UnicornStudio && typeof window.UnicornStudio.init === 'function') {
          init();
        } else {
          const existing = document.querySelector('script[data-unicorn-sdk="true"]');
          const onLoad = () => init();
          if (existing) {
            existing.addEventListener('load', onLoad, { once: true });
            cleanups.push(() => existing.removeEventListener('load', onLoad));
          } else {
            const script = document.createElement('script');
            script.src =
              'https://cdn.jsdelivr.net/gh/hiunicornstudio/unicornstudio.js@v2.1.0/dist/unicornStudio.umd.js';
            script.async = true;
            script.dataset.unicornSdk = 'true';
            script.addEventListener('load', onLoad);
            document.body.appendChild(script);
            cleanups.push(() => script.removeEventListener('load', onLoad));
          }
        }
      }
    }

    return () => {
      cleanups.forEach((fn) => fn());
    };
  }, []);

  return (
    <div className="landing-root" ref={rootRef}>
      <header className="landing-nav reveal" id="landing-nav">
        <div className="landing-container landing-nav__inner">
          <a className="landing-logo" href="#hero">
            Dala Network
          </a>
          <div className="landing-nav__meta">
            <div className="lang-switch">
              <button
                type="button"
                className={`lang-switch__btn ${language === 'ru' ? 'lang-switch__btn--active' : ''}`}
                onClick={() => onLanguageChange('ru')}
              >
                RU
              </button>
              <span className="lang-switch__sep">|</span>
              <button
                type="button"
                className={`lang-switch__btn ${language === 'en' ? 'lang-switch__btn--active' : ''}`}
                onClick={() => onLanguageChange('en')}
              >
                ENG
              </button>
            </div>
            <a className="btn btn-ghost" href={GITHUB_URL} target="_blank" rel="noreferrer">
              {t.readDocs}
            </a>
          </div>
        </div>
      </header>

      <section className="landing-hero hero" id="hero">
        {/* Фон и эффекты */}
        <div className="landing-hero__bg">
          <div
            data-us-project="lFqI94GW0JcxJNk1NH4n"
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
          ></div>
        </div>
        <div className="landing-hero__overlay" />
        <div className="orb orb-1" />
        <div className="orb orb-2" />

        {/* Главный контент */}
        <div className="landing-hero__content hero__content reveal">
          <div className="hero-badge hero__badge">
            <span className="hero-badge__live hero__badge-new">{t.heroLive}</span>
            <span style={{ marginLeft: '8px' }}>{t.heroBadge}</span>
          </div>

          <h1 className="hero__title">
            {t.heroTitleTop}
            <br />
            <em>{t.heroTitleBottom}</em>
          </h1>

          <p className="hero__sub">{t.heroSub}</p>

          <div className="hero-actions hero__actions">
            <button
              className="btn btn-primary btn-pill btn-hero-primary"
              type="button"
              onClick={onLaunch}
            >
              {t.launchApp}
            </button>
            <a
              className="btn btn-ghost btn-pill btn-hero-ghost"
              href="https://github.com/iaqool/agri-subsidy"
              target="_blank"
              rel="noreferrer"
            >
              {t.readDocs}
            </a>
          </div>

          {/* Метрики */}
          <div className="hero-stats hero__stats">
            <div className="hero__stat">
              <strong className="hero__stat-value">~13s</strong>
              <span className="hero__stat-label">{t.heroStats[0]}</span>
            </div>
            <div className="hero__stat">
              <strong className="hero__stat-value">10m</strong>
              <span className="hero__stat-label">{t.heroStats[1]}</span>
            </div>
            <div className="hero__stat">
              <strong className="hero__stat-value">100%</strong>
              <span className="hero__stat-label">{t.heroStats[2]}</span>
            </div>
            <div className="hero__stat">
              <strong className="hero__stat-value">M-of-N</strong>
              <span className="hero__stat-label">{t.heroStats[3]}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="logos" id="infrastructure">
        <div className="landing-container">
          <p className="logos__label">{t.infraLabel}</p>
          <div className="logos__viewport">
            <div className="logos__track">
              {[...logos, ...logos].map((item, index) => (
                <span className="logos__item" key={`${item}-${index}`}>
                  {item}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section" id="features">
        <div id="featureParticles" className="particles" />
        <div className="landing-container">
          <div className="section-head reveal">
            <span className="section-kicker">{t.capabilitiesKicker}</span>
            <h2>{t.capabilitiesTitle}</h2>
            <p>{t.capabilitiesDescription}</p>
          </div>
          <div className="feature-grid stagger">
            {t.featureCards.map((card) => (
              <article key={card.title} className="tilt-card feature-card">
                <div className="feature-status">{card.status}</div>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
            <article className="tilt-card feature-card feature-card--wide">
              <h3>{t.integrationsTitle}</h3>
              <p>{t.integrationsDescription}</p>
              <div id="integrationBadges" className="integration-badges" />
              <div id="waveform" className="waveform" />
            </article>
          </div>
        </div>
      </section>

      <section className="landing-section" id="architecture">
        <div className="landing-container architecture-grid">
          <div className="reveal">
            <span className="section-kicker">{t.howItWorksKicker}</span>
            <h2>{t.howItWorksTitle}</h2>
            <ol className="steps">
              {t.steps.map((step) => (
                <li key={step.title}>
                  <strong>{step.title}</strong>
                  <span>{step.body}</span>
                </li>
              ))}
            </ol>
          </div>
          <aside className="tilt-card dashboard-card reveal">
            <h3>{t.liveOracleTitle}</h3>
            <p>{t.liveOracleDescription}</p>
            <div className="dashboard-bars" id="dashBars" />
            <div className="metrics-inline">
              <div>
                <b data-count="2">0</b>
                <span>{t.minEvalLabel}</span>
              </div>
              <div>
                <b data-count="99.98">0</b>
                <span>{t.policyPassLabel}</span>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section className="landing-section vision" id="vision">
        <div className="landing-container">
          <div className="section-head reveal">
            <span className="section-kicker">{t.problemVisionKicker}</span>
            <h2>{t.problemVisionTitle}</h2>
          </div>
          <div className="vision-grid stagger">
            <article className="tilt-card vision-card">
              <div className="vision-card__kicker">{t.problemKicker}</div>
              <p>{t.problemText}</p>
            </article>
            <article className="tilt-card vision-card vision-card--solution">
              <div className="vision-card__kicker">{t.solutionKicker}</div>
              <p>{t.solutionText}</p>
            </article>
          </div>
        </div>
      </section>

      <section className="landing-section" id="customer">
        <div className="landing-container">
          <div className="section-head reveal">
            <span className="section-kicker">{t.customerKicker}</span>
            <h2>{t.customerTitle}</h2>
          </div>
          <div className="feature-grid stagger">
            {t.customerCards.map((card) => (
              <article key={card.title} className="tilt-card feature-card">
                <div className="feature-status">{card.status}</div>
                <h3>{card.title}</h3>
                <p>{card.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section" id="roadmap">
        <div className="landing-container">
          <div className="section-head reveal">
            <span className="section-kicker">{t.roadmapKicker}</span>
            <h2>{t.roadmapTitle}</h2>
          </div>
          <ol className="roadmap-list stagger">
            {t.roadmapItems.map((item, idx) => (
              <li
                key={`${item.tag}-${idx}`}
                className={`roadmap-item${item.done ? ' roadmap-item--done' : ''}`}
              >
                <span className="roadmap-item__tag">{item.tag}</span>
                <span className="roadmap-item__text">{item.text}</span>
                <span className="roadmap-item__status">{item.done ? '● shipped' : '○ planned'}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="landing-section cta">
        <div id="ctaParticles" className="particles" />
        <div className="landing-container">
          <div className="cta-panel reveal">
            <h2>{t.ctaTitle}</h2>
            <p>{t.ctaDescription}</p>
            <div className="cta-actions">
              <button type="button" className="btn btn-primary" onClick={onLaunch}>
                {t.launchApp}
              </button>
              <a href={GITHUB_URL} className="btn btn-ghost" target="_blank" rel="noreferrer">
                {t.readDocs}
              </a>
            </div>
            <div className="sparkline-row">
              <div id="spark1" className="sparkline" />
              <div id="spark2" className="sparkline" />
            </div>
          </div>
        </div>
      </section>

      <footer className="landing-footer reveal">
        <div className="landing-container landing-footer__inner">
          <p>
            &copy; <span id="footerYear" /> Dala Network
          </p>
          <div>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
            <a href="https://explorer.solana.com/?cluster=devnet" target="_blank" rel="noreferrer">
              Solana Devnet
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
