import { useEffect, useRef } from 'react';
import './landing.css';

const GITHUB_URL = 'https://github.com/iaqool/agri-subsidy';

const logos = [
  'Solana',
  'Anchor',
  'OpenAI',
  'Sentinel NDVI',
  'Copernicus',
  'Pyth',
  'Switchboard',
  'Helius',
];

const localizedCopy = {
  ru: {
    readDocs: 'Документация',
    launchApp: 'Открыть дашборд',
    heroLive: 'LIVE ON DEVNET',
    heroBadge: 'Усиливаем степь ончейн-интеллектом →',
    heroTitleTop: 'Находим сигнал сквозь засуху —',
    heroTitleBottom: 'до того, как потерян урожай.',
    heroSub:
      'Публичная инфраструктура выплат для агросектора. Архитектура Dual-Validation убирает слепое доверие: OpenAI анализирует спутниковые данные, а Anchor-контракт контролирует выдачу средств.',
    heroStats: ['ФИНАЛИЗАЦИЯ TX', 'РАЗРЕШЕНИЕ NDVI', 'ОНЧЕЙН-КОНТРОЛЬ', 'ЧЕЛОВЕЧЕСКИЙ ФАКТОР'],
    infraLabel: 'Инфраструктурный стек',
    capabilitiesKicker: 'Возможности',
    capabilitiesTitle: 'Безопасная связка AI + спутники + смарт-контракты',
    capabilitiesDescription:
      'Ключевые модули адаптированы под Dala Network для хакатон-демо и безопасного продакшн-пути.',
    featureCards: [
      {
        title: 'Спутниковый NDVI ingest',
        body: 'Нормализуем NDVI Sentinel и климатический контекст по регионам выплат в реальном времени.',
        status: '847K тайлов/день',
      },
      {
        title: 'Скоринг засухи через OpenAI',
        body: 'AI считает объяснимый композитный скор и приоритизирует решения по климатической поддержке.',
        status: '97.3% доверия',
      },
      {
        title: 'Dual-Validation в Anchor',
        body: 'AI рекомендует офчейн, но финальная безопасность выплат жестко проверяется ончейн-порогами.',
        status: '0 небезопасных tx',
      },
    ],
    integrationsTitle: 'Компонентные интеграции',
    integrationsDescription:
      'Все, что нужно для детерминированной инфраструктуры публичных выплат.',
    howItWorksKicker: 'Как это работает',
    howItWorksTitle: 'От NDVI-сигнала до ончейн-выплаты',
    steps: [
      {
        title: '1. Сбор данных',
        body: 'Спутниковые и климатические фиды нормализуются по регионам.',
      },
      {
        title: '2. Скоринг в OpenAI',
        body: 'AI формирует объяснимый индекс тяжести засухи.',
      },
      {
        title: '3. Валидация через Anchor',
        body: 'Контрактные guardrails проверяют строгие пороги выплат.',
      },
      {
        title: '4. Безопасная выдача',
        body: 'Одобренные выплаты исполняются в Solana с полным аудит-трейлом.',
      },
    ],
    liveOracleTitle: 'Пульс оракула',
    liveOracleDescription: 'Таймлайн Dual-Validation и тренд пропускной способности.',
    minEvalLabel: 'мин оценка',
    policyPassLabel: 'прохождение policy %',
    problemVisionKicker: 'Проблема и видение',
    problemVisionTitle: 'Пересобираем климатические выплаты для реального эффекта',
    problemKicker: 'Проблема',
    problemText:
      'Климатические шоки участились, но господдержка остается ручной, фрагментированной и уязвимой к коррупции. Фермеры ждут месяцами.',
    solutionKicker: 'Решение',
    solutionText:
      'Параметрическая RWA-инфраструктура: используем спутниковый NDVI и AI, чтобы быстро подтверждать ущерб и автоматически запускать выплаты через смарт-контракты Solana.',
    ctaTitle: 'Быстрая помощь, усиленная политикой.',
    ctaDescription:
      'Откройте дашборд, чтобы запустить AI-оценку и проверить ончейн-предохранители.',
  },
  en: {
    readDocs: 'Read Docs',
    launchApp: 'Launch App',
    heroLive: 'LIVE ON DEVNET',
    heroBadge: 'Empowering the Steppe with On-Chain Intelligence →',
    heroTitleTop: 'Find the signal through the drought —',
    heroTitleBottom: 'before the harvest is lost.',
    heroSub:
      'A public-benefit payout rail for the agricultural sector. Our Dual-Validation architecture ensures zero trust: OpenAI analyzes satellite data, but the Anchor smart contract controls the funds.',
    heroStats: ['TX FINALITY', 'NDVI RESOLUTION', 'ON-CHAIN ENFORCEMENT', 'HUMAN BIAS'],
    infraLabel: 'Infrastructure stack',
    capabilitiesKicker: 'Capabilities',
    capabilitiesTitle: 'Secure AI + Satellite + Smart Contracts',
    capabilitiesDescription:
      'Core modules adapted to Dala Network for hackathon demo and safe production path.',
    featureCards: [
      {
        title: 'NDVI Satellite Ingestion',
        body: 'Normalize Sentinel-derived NDVI + climate context in real time for each payout region.',
        status: '847K tiles/day',
      },
      {
        title: 'OpenAI Drought Scoring',
        body: 'AI computes explainable composite severity scores to prioritize climate-relief decisions.',
        status: '97.3% confidence',
      },
      {
        title: 'Anchor Dual-Validation',
        body: 'AI recommends off-chain, but on-chain policy thresholds enforce final payout safety.',
        status: '0 unsafe tx',
      },
    ],
    integrationsTitle: 'Composable Integrations',
    integrationsDescription: 'Everything needed for a deterministic public-benefit payout rail.',
    howItWorksKicker: 'How it works',
    howItWorksTitle: 'From NDVI signal to on-chain relief',
    steps: [
      {
        title: '1. Ingest data',
        body: 'Satellite and climate feeds are normalized by region.',
      },
      {
        title: '2. Score with OpenAI',
        body: 'AI produces explainable drought severity scores.',
      },
      {
        title: '3. Enforce with Anchor',
        body: 'Contract guardrails validate strict payout thresholds.',
      },
      {
        title: '4. Disburse safely',
        body: 'Approved payouts execute on Solana with full audit trail.',
      },
    ],
    liveOracleTitle: 'Live Oracle Pulse',
    liveOracleDescription: 'Dual-Validation timeline and throughput trend.',
    minEvalLabel: 'min eval',
    policyPassLabel: 'policy pass %',
    problemVisionKicker: 'The Problem & Vision',
    problemVisionTitle: 'Rebuilding climate relief rails for real-world impact',
    problemKicker: 'The Problem',
    problemText:
      'Climate shocks are frequent, but government relief is manual, fragmented, and prone to corruption. Farmers wait months for help.',
    solutionKicker: 'The Solution',
    solutionText:
      'Parametric RWA infrastructure. We use Sentinel NDVI satellite data and AI to instantly verify drought impact, triggering automated payouts via Solana smart contracts.',
    ctaTitle: 'Fast relief, enforced by policy.',
    ctaDescription: 'Open the dashboard to run AI evaluation and verify on-chain safety checks.',
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
              <strong className="hero__stat-value">~400ms</strong>
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
              <strong className="hero__stat-value">0%</strong>
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
