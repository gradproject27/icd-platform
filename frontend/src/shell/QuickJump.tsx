import { useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { IconSearch } from "../components/icons";

/**
 * Incident-ID quick jump: opens /incidents/<id> as typed. No endpoint is called here; an unknown
 * ID shows the detail page's normal not-found state.
 */
export function QuickJump() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const inputId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const id = value.trim();
    if (!id) return;
    navigate(`/incidents/${encodeURIComponent(id)}`);
    setValue("");
  };

  return (
    <form className="quick-jump" role="search" aria-label="Go to incident" onSubmit={submit}>
      <label htmlFor={inputId} className="quick-jump__label">
        Incident ID
      </label>
      <span className="quick-jump__field">
        <IconSearch />
        <input
          id={inputId}
          type="text"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          placeholder="inc-…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </span>
      <button type="submit">Go</button>
    </form>
  );
}
