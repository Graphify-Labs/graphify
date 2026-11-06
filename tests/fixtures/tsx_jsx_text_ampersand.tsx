// #2922 — bare ``&`` in JSX text breaks the TSX grammar and drops symbols.
// tree-sitter-typescript requires ``&`` in JSX text (the run between ``>``
// and ``<`` inside a JSX element) to begin an HTML entity reference; a bare
// ``&`` produces an ERROR node and the partial-extraction path surfaces a
// parse_errors warning (#2551). Before the fix, this file extracted to a
// single file node — every function, class, and import was silently lost.
// After the fix, the bare ``&`` in JSX text is masked to ``&amp;`` and every
// node below extracts cleanly with no parse_errors.

import { helper } from "./helper";

const FLAG_MASK = 0xff & 0x0f;

export function Page() {
    return (
        <div className="page">
            <h1>VoIP & Chamadas</h1>
            <h2>Conexões & Integrações</h2>
            <p>
                Welcome & hello. Mixed & multiple & ampersands.
            </p>
            <span title="VoIP & SIP" />
            <a href="/search?q=a&b=c">link</a>
            <ul>
                {items.filter((it) => it.flag && it.visible).map((it) => (
                    <li key={it.id}>{it.label}</li>
                ))}
            </ul>
        </div>
    );
}

export class Component extends React.Component {
    render() {
        return (
            <section>
                <header>A & B</header>
                <footer>{helper(FLAG_MASK)}</footer>
            </section>
        );
    }
}

export const fragment = (
    <>
        <span>one & two</span>
        <span>three &amp; four</span>
    </>
);