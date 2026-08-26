import { render, screen } from "@testing-library/react";
import { AgentAvatar } from "../AgentAvatar";

describe("AgentAvatar", () => {
  it("renders the letter P", () => {
    render(<AgentAvatar />);
    expect(screen.getByText("P")).toBeInTheDocument();
  });

  it("uses the shared Newma semantic gradient", () => {
    const { container } = render(<AgentAvatar />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toMatch(/bg-gradient/);
    expect(el.className).toContain("from-primary");
    expect(el.className).toContain("to-warning");
    expect(el.className).not.toMatch(/#|blue|cyan|violet/);
  });
});
