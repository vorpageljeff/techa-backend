import { API_BASE_URL, APP_URL } from './config';

const services = [
  {
    title: 'NDVI e satelite',
    text: 'Acompanhe vigor vegetativo e sinais de estresse sem depender de visita manual em toda a area.',
  },
  {
    title: 'Alertas por talhao',
    text: 'Centralize fazendas, talhoes e anomalias em uma rotina simples para tomada de decisao.',
  },
  {
    title: 'Relatorios operacionais',
    text: 'Use historico, area afetada e dados de campo para transformar observacao em acao.',
  },
];

const metrics = [
  ['API', 'online'],
  ['Banco', 'conectado'],
  ['App', 'web/mobile'],
  ['Deploy', 'Render + Vercel'],
];

export function App() {
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Techa">
          <span className="brandMark">T</span>
          <span>Techa</span>
        </a>
        <nav className="nav" aria-label="Principal">
          <a href="#produto">Produto</a>
          <a href="#como-funciona">Como funciona</a>
          <a href="#contato">Contato</a>
          <a className="navCta" href={APP_URL} target="_blank" rel="noreferrer">
            Entrar no app
          </a>
        </nav>
      </header>

      <main>
        <section id="home" className="hero">
          <div className="heroMedia" aria-hidden="true" />
          <div className="heroContent">
            <p className="eyebrow">Monitoramento agricola por satelite</p>
            <h1>Inteligencia de campo para enxergar o talhao antes do prejuizo.</h1>
            <p className="heroText">
              O Techa combina cadastro de fazendas, talhoes, NDVI e alertas para
              apoiar produtores e consultores na rotina de acompanhamento agricola.
            </p>
            <div className="heroActions">
              <a className="primary" href={APP_URL} target="_blank" rel="noreferrer">
                Acessar app
              </a>
              <a className="secondary" href={`${API_BASE_URL}/health`} target="_blank" rel="noreferrer">
                Ver status da API
              </a>
            </div>
          </div>
          <div className="metrics" aria-label="Status da plataforma">
            {metrics.map(([label, value]) => (
              <div className="metric" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </section>

        <section id="produto" className="section">
          <div className="sectionHeader">
            <p className="eyebrow">Produto</p>
            <h2>O que ja da para adaptar deste front ao projeto</h2>
            <p>
              A pasta adicionada era uma landing institucional. Ela nao substitui o
              app operacional, mas encaixa muito bem como site publico no Vercel,
              apontando para o app e para a API ja publicados.
            </p>
          </div>
          <div className="serviceGrid">
            {services.map((service) => (
              <article className="service" key={service.title}>
                <h3>{service.title}</h3>
                <p>{service.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="como-funciona" className="band">
          <div>
            <p className="eyebrow">Fluxo</p>
            <h2>Site publico, app logado e backend separados.</h2>
          </div>
          <ol className="steps">
            <li>
              <strong>Site</strong>
              <span>Apresenta a solucao e leva o usuario para cadastro/login.</span>
            </li>
            <li>
              <strong>App</strong>
              <span>Opera fazendas, talhoes, dashboard e conta autenticada.</span>
            </li>
            <li>
              <strong>API</strong>
              <span>Render segura autenticacao, banco, Redis e regras de negocio.</span>
            </li>
          </ol>
        </section>

        <section id="contato" className="section contact">
          <div>
            <p className="eyebrow">Contato</p>
            <h2>Pronto para validar com usuario real.</h2>
            <p>
              O proximo ganho pratico e trocar o poligono de teste por desenho no
              mapa e adicionar captura de leads neste site.
            </p>
          </div>
          <div className="contactPanel">
            <span>Backend</span>
            <a href={API_BASE_URL} target="_blank" rel="noreferrer">{API_BASE_URL}</a>
            <span>Aplicacao</span>
            <a href={APP_URL} target="_blank" rel="noreferrer">{APP_URL}</a>
          </div>
        </section>
      </main>
    </div>
  );
}
