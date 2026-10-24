import { useEffect, useState } from "react";
import { Crest } from "./Crest";

interface LeagueClub {
  id: string;
  name: string;
  short: string;
  primary: string;
  secondary: string;
  formation: string;
  nickname: string;
  ground: string;
  city: string;
  founded: number;
  style: string;
  rival: string | null;
  form: string[];
}
interface Row {
  position: number;
  club: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
  xg_for: number;
  xg_against: number;
}
interface Meeting {
  season: "last" | "this";
  matchday: number;
  home: string;
  away: string;
  score: [number, number];
}
interface Fixture {
  home: string;
  away: string;
  scenario: string;
  title: string;
  story: string;
  h2h: Meeting[];
}
interface Result {
  matchday: number;
  home: string;
  away: string;
  score: [number, number];
  xg: [number, number];
}
interface Scorer {
  player_id: string;
  name: string;
  club: string;
  goals: number;
  shots: number;
  xg: number;
  goals_above_xg: number;
}
interface LeagueData {
  matchday: number;
  clubs: Record<string, LeagueClub>;
  table: Row[];
  results: Result[];
  fixtures: Fixture[];
  players: Scorer[];
}

function Form({ form }: { form: string[] }) {
  return (
    <span className="lg-form">
      {form.map((f, i) => (
        <i key={i} className={`f${f}`}>
          {f}
        </i>
      ))}
    </span>
  );
}

function Side({ c, pos, away }: { c: LeagueClub; pos?: number; away?: boolean }) {
  return (
    <div className={`lg-fx-side ${away ? "away" : ""}`}>
      <Crest club={c} size={56} />
      <div>
        <b>{c.name}</b>
        <span className="label">
          {pos}
          {ord(pos)} in the table
        </span>
        <Form form={c.form} />
      </div>
    </div>
  );
}

function FixtureRow({ f, clubs, table, onWatch }: { f: Fixture; clubs: Record<string, LeagueClub>; table: Row[]; onWatch: (id: string) => void }) {
  const h = clubs[f.home];
  const a = clubs[f.away];
  const pos = (id: string) => table.find((r) => r.club === id)?.position;
  const last = f.h2h[0];
  return (
    <article className="lg-fx" style={{ ["--h" as string]: h.primary, ["--a" as string]: a.primary }}>
      <div className="lg-fx-story">
        <div className="lg-fx-kicker">
          <span className="lg-tag">{f.title}</span>
          {h.rival === a.id && <span className="lg-derby">Derby</span>}
        </div>
        <p>{f.story}</p>
      </div>
      <Side c={h} pos={pos(h.id)} />
      <div className="lg-fx-vs">
        <b>V</b>
        <span className="label">{h.ground}</span>
      </div>
      <Side c={a} pos={pos(a.id)} away />
      <div className="lg-fx-foot">
        <button onClick={() => onWatch(f.scenario)}>Watch live &#9656;</button>
        <span className="label">
          {last ? `Last met ${clubs[last.home].short} ${last.score[0]}-${last.score[1]} ${clubs[last.away].short}` : "First meeting"}
        </span>
      </div>
    </article>
  );
}

function ClubDetail({ c, data }: { c: LeagueClub; data: LeagueData }) {
  const row = data.table.find((r) => r.club === c.id);
  const scorer = data.players.find((p) => p.club === c.id);
  const results = data.results.filter((r) => r.home === c.id || r.away === c.id).slice(-3).reverse();
  const next = data.fixtures.find((f) => f.home === c.id || f.away === c.id);
  const rival = c.rival ? data.clubs[c.rival] : null;
  return (
    <div className="lg-cd" style={{ ["--c" as string]: c.primary }}>
      <div className="lg-cd-id">
        <Crest club={c} size={120} />
        <div>
          <span className="label">
            {c.nickname} &middot; Est. {c.founded}
          </span>
          <h3>{c.name}</h3>
          <p>{c.style}.</p>
          <span className="label dim">
            {c.ground}, {c.city} &middot; {c.formation}
            {rival ? ` · Rivals: ${rival.name}` : ""}
          </span>
        </div>
      </div>
      <div className="lg-cd-stats">
        <div>
          <b className="num">
            {row?.position}
            <small>{ord(row?.position)}</small>
          </b>
          <span className="label">{row?.points} pts</span>
        </div>
        <div>
          <b className="num">{row ? sign(row.gd) : ""}</b>
          <span className="label">Goal diff</span>
        </div>
        <div>
          <b className="num">{row ? (row.xg_for - row.xg_against).toFixed(1) : ""}</b>
          <span className="label">xG diff</span>
        </div>
        <div>
          <Form form={c.form} />
          <span className="label">Form</span>
        </div>
      </div>
      <div className="lg-cd-more">
        <div>
          <span className="label">Top scorer</span>
          <b>{scorer ? `${scorer.name}, ${scorer.goals}` : "No one in the top 20"}</b>
        </div>
        <div>
          <span className="label">Recent results</span>
          {results.map((r) => {
            const home = r.home === c.id;
            const opp = data.clubs[home ? r.away : r.home];
            return (
              <b key={r.matchday} className="num">
                MD{r.matchday} {home ? "v" : "at"} {opp.short} {r.score[0]}-{r.score[1]}
              </b>
            );
          })}
        </div>
        {next && (
          <div>
            <span className="label">Matchday {data.matchday}</span>
            <b>{next.title}</b>
            <a href="#/league" onClick={(e) => (e.preventDefault(), window.scrollTo({ top: 0, behavior: "smooth" }))}>
              {data.clubs[next.home].short} v {data.clubs[next.away].short} &#8593;
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

const ord = (n?: number) => (!n ? "" : n === 1 ? "st" : n === 2 ? "nd" : n === 3 ? "rd" : "th");
const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`);

/** The league around the live match: this matchday's fixtures, the table, the clubs and the scorers. */
export function League({ onWatch }: { onWatch: (scenario: string) => void }) {
  const [data, setData] = useState<LeagueData | null>(null);
  const [md, setMd] = useState<number | null>(null);
  const [pick, setPick] = useState("KR");
  useEffect(() => {
    fetch("/api/league")
      .then((r) => r.json())
      .then((d: LeagueData) => {
        setData(d);
        setMd(d.matchday - 1);
      })
      .catch(() => setData(null));
  }, []);
  if (!data) return <div className="empty" style={{ padding: 24 }}>Loading the league.</div>;
  const { clubs, table } = data;
  const played = Array.from({ length: data.matchday - 1 }, (_, i) => i + 1);
  return (
    <div className="lg">
      <section className="lg-hero">
        <span className="label">The Meridian League &middot; Season so far</span>
        <h1>Matchday {data.matchday}</h1>
        <p>Five matches, five stories. Every result, table position and goal below was played by the same simulator that runs the live match.</p>
      </section>

      <section className="lg-fixtures">
        {data.fixtures.map((f) => (
          <FixtureRow key={f.scenario} f={f} clubs={clubs} table={table} onWatch={onWatch} />
        ))}
      </section>

      <div className="lg-two">
        <section className="lg-panel">
          <h2 className="lg-h">Table</h2>
          <table className="lg-table num">
            <thead>
              <tr>
                <th />
                <th className="l">Club</th>
                <th>P</th>
                <th>W</th>
                <th>D</th>
                <th>L</th>
                <th>GD</th>
                <th title="Expected goals for and against">xG</th>
                <th className="l">Form</th>
                <th>Pts</th>
              </tr>
            </thead>
            <tbody>
              {table.map((r) => {
                const c = clubs[r.club];
                return (
                  <tr key={r.club} style={{ ["--c" as string]: c.primary }}>
                    <td className="pos">{r.position}</td>
                    <td className="l">
                      <div className="club">
                        <Crest club={c} size={26} />
                        <span>{c.name}</span>
                      </div>
                    </td>
                    <td>{r.played}</td>
                    <td>{r.won}</td>
                    <td>{r.drawn}</td>
                    <td>{r.lost}</td>
                    <td>{sign(r.gd)}</td>
                    <td className="dim">
                      {r.xg_for.toFixed(1)}&ndash;{r.xg_against.toFixed(1)}
                    </td>
                    <td className="l">
                      <Form form={c.form} />
                    </td>
                    <td className="pts">{r.points}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section className="lg-panel">
          <h2 className="lg-h">Top scorers</h2>
          <div className="lg-scorers">
            {data.players.slice(0, 8).map((p, i) => {
              const c = clubs[p.club];
              return (
                <div key={p.player_id} className="lg-scorer" style={{ ["--c" as string]: c.primary }}>
                  <span className="rk num">{i + 1}</span>
                  <Crest club={c} size={28} />
                  <div>
                    <b>{p.name}</b>
                    <span className="label">
                      {c.name} &middot; {p.shots} shots &middot; {p.xg.toFixed(1)} xG
                    </span>
                  </div>
                  <span className={`gax num ${p.goals_above_xg >= 0 ? "up" : "down"}`} title="Goals above expected">
                    {sign(Number(p.goals_above_xg.toFixed(1)))}
                  </span>
                  <span className="g num">{p.goals}</span>
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <section className="lg-panel">
        <div className="lg-results-head">
          <h2 className="lg-h">Results</h2>
          <div className="lg-mds">
            {played.map((n) => (
              <button key={n} className={md === n ? "on" : ""} onClick={() => setMd(n)}>
                {n}
              </button>
            ))}
          </div>
        </div>
        <div className="lg-results">
          {data.results
            .filter((r) => r.matchday === md)
            .map((r) => {
              const h = clubs[r.home];
              const a = clubs[r.away];
              const [hg, ag] = r.score;
              return (
                <div key={r.home} className="lg-res">
                  <div className={`t ${hg < ag ? "lost" : ""}`}>
                    <Crest club={h} size={22} />
                    {h.name}
                  </div>
                  <b className="num">
                    {hg}&ndash;{ag}
                  </b>
                  <div className={`t r ${ag < hg ? "lost" : ""}`}>
                    {a.name}
                    <Crest club={a} size={22} />
                  </div>
                  <span className="xg num">
                    xG {r.xg[0].toFixed(2)} &ndash; {r.xg[1].toFixed(2)}
                  </span>
                </div>
              );
            })}
        </div>
      </section>

      <section className="lg-panel">
        <h2 className="lg-h">The clubs</h2>
        <div className="lg-crests" role="tablist">
          {Object.values(clubs).map((c) => (
            <button key={c.id} role="tab" aria-selected={pick === c.id} className={pick === c.id ? "on" : ""} onClick={() => setPick(c.id)} title={c.name} style={{ ["--c" as string]: c.primary }}>
              <Crest club={c} size={44} />
              <span>{c.short}</span>
            </button>
          ))}
        </div>
        <ClubDetail c={clubs[pick]} data={data} />
      </section>
    </div>
  );
}
