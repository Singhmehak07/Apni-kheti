import Icon from "./Icon.jsx";
import SpeakButton from "./SpeakButton.jsx";

/** Big tappable answer cards: icon + label, each with its own speaker so options can be heard. */
export default function OptionGrid({ options, onPick, selected, disabled, cols = 2, field }) {
  const grid = cols === 3 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-1 min-[420px]:grid-cols-2";
  return (
    <ul className={`grid gap-2.5 ${grid}`} role="list">
      {options.map((o) => {
        const on = selected === o.id;
        return (
          <li key={o.id} className={`card relative flex items-stretch overflow-hidden transition-colors ${on ? "border-ink ring-2 ring-ink" : "hover:border-[#cfcdc9]"}`}>
            <button type="button" disabled={disabled} onClick={() => onPick(o)} data-testid={`opt-${field}-${o.id}`}
              data-read={o.label}
              className="flex min-h-16 flex-1 items-center gap-3 px-3.5 py-3 text-left disabled:opacity-60">
              <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[8px] bg-sunken text-ink">
                <Icon name={o.icon} size={24} />
              </span>
              <span className="min-w-0">
                <span className="block text-[17px] font-semibold leading-snug">{o.label}</span>
                {o.sub && <span className="block text-[14px] text-muted">{o.sub}</span>}
              </span>
            </button>
            <span className="flex items-center pr-2"><SpeakButton text={o.label} size="sm" tone="quiet" label={o.label} /></span>
          </li>
        );
      })}
    </ul>
  );
}
