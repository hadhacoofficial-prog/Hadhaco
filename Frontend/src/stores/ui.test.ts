import { useUi } from "./ui";

beforeEach(() => {
  useUi.setState({ searchOpen: false });
});

describe("useUi.openSearch", () => {
  it("sets searchOpen to true", () => {
    useUi.getState().openSearch();
    expect(useUi.getState().searchOpen).toBe(true);
  });

  it("is idempotent when already open", () => {
    useUi.setState({ searchOpen: true });
    useUi.getState().openSearch();
    expect(useUi.getState().searchOpen).toBe(true);
  });
});

describe("useUi.closeSearch", () => {
  it("sets searchOpen to false", () => {
    useUi.setState({ searchOpen: true });
    useUi.getState().closeSearch();
    expect(useUi.getState().searchOpen).toBe(false);
  });

  it("is idempotent when already closed", () => {
    useUi.getState().closeSearch();
    expect(useUi.getState().searchOpen).toBe(false);
  });
});

describe("useUi.toggleSearch", () => {
  it("opens the search panel when it is closed", () => {
    useUi.getState().toggleSearch();
    expect(useUi.getState().searchOpen).toBe(true);
  });

  it("closes the search panel when it is open", () => {
    useUi.setState({ searchOpen: true });
    useUi.getState().toggleSearch();
    expect(useUi.getState().searchOpen).toBe(false);
  });

  it("toggling twice returns to the original state", () => {
    const initial = useUi.getState().searchOpen;
    useUi.getState().toggleSearch();
    useUi.getState().toggleSearch();
    expect(useUi.getState().searchOpen).toBe(initial);
  });
});
