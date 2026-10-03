"""What a recorded lesson teaches, past its opening line.

Twenty minutes of a lesson is a heading, paragraphs that explain each step and
why it matters, a checklist and a reminder, every claim cited to the knowledge
base chunk it comes from. The recordings and the machine runs share these
bodies, so a lesson is as long in a test as on the page.
"""
from __future__ import annotations


def _p(text: str, *cites: str) -> dict:
    return {"type": "paragraph", "text": text, "cites": list(cites)}


BENCH = (
    {"type": "heading", "text": "Why the bench comes first"},
    _p("Most hand injuries in a workshop begin on a cluttered bench. An offcut rolls under the work and tips "
       "it, a chisel lies edge up under a rag, or a spill lets a clamp slip at the moment you lean on it. "
       "Clearing the bench is the first step of every job, not something left for the end of the day.",
       "mt-kb-012"),
    _p("Keep only the tools for the step you are on, laid flat with their edges facing away from you and "
       "towards the back of the bench. When the step is done, put each tool back in its rack. A tool left out "
       "is a tool that falls, and a falling chisel is caught by reflex far more often than it should be.",
       "mt-kb-013"),
    _p("Wipe a spill of glue, oil or finish straight away with a dry cloth, then put the cloth in the lidded "
       "bin rather than on the bench, because oily cloths left in a heap can heat up on their own. A dry bench "
       "also keeps the work from sliding while it is held in the vice.", "mt-kb-014"),
    {"type": "checklist", "items": ["offcuts cleared from the bench and the floor around it",
                                    "only the tools for this step out, edges away and to the back",
                                    "spills wiped dry and the cloth in the lidded bin",
                                    "each tool back in its rack when the step is done"]},
    {"type": "callout", "text": "If you reach for a tool and have to move something else first, stop and clear "
                                "the bench before you carry on."},
)
TOOLS = (
    {"type": "heading", "text": "A check before every use"},
    _p("Before a tool is used it is looked at, every time. A split in a wooden handle, a mushroomed head on a "
       "cold chisel or a loose ferrule will fail under load, and it fails without warning. The check takes "
       "less than a minute and is done before the tool touches the work.", "mt-kb-015"),
    _p("Hold the handle and twist it against the blade: any movement means it is loose. Run a thumb along the "
       "handle to feel for cracks, and look at the striking end for burrs or splinters. A tool that fails any "
       "of these checks is taken out of use at once and put in the red tray for the workshop lead.",
       "mt-kb-016"),
    _p("A damaged tool is never patched at the bench with tape or glue. Tag it with the fault and the date and "
       "hand it to the workshop lead, and nobody else decides what happens to it. A shared tool left damaged "
       "on the rack puts the next person at risk without their knowing.", "mt-kb-017"),
    {"type": "checklist", "items": ["handle twisted against the blade: no movement",
                                    "handle felt along its length: no cracks or splits",
                                    "striking end looked at: no burrs, splinters or mushrooming",
                                    "anything that fails is taken out of use, tagged and put in the red tray"]},
    {"type": "callout", "text": "A tool you are unsure about is a tool that fails the check."},
)
DUST = (
    {"type": "heading", "text": "Extraction before the first cut"},
    _p("Fine wood dust is the hazard nobody sees. It hangs in the air long after a cut and settles deep in the "
       "lungs. Extraction catches it at the source, so the hose is connected and the extractor switched on "
       "before the machine starts, not after the first cut has already filled the air.", "mt-kb-018"),
    _p("Check that the hose is seated firmly on the machine's port, that the blast gate for that machine is "
       "open, and that every other gate is closed. A gate left open elsewhere halves the suction where you need "
       "it. A hose that kinks or rests on the floor will choke and stop pulling dust.", "mt-kb-019"),
    _p("Empty the collection bag at the end of a run, before it is more than two thirds full, wearing a mask "
       "and gloves. Lower the bag slowly into a sealed sack rather than shaking it out. A full bag stops the "
       "extractor drawing air, and the dust then escapes through every gap in the system.", "mt-kb-020"),
    {"type": "checklist", "items": ["hose seated on the machine port and not kinked",
                                    "this machine's blast gate open, every other gate closed",
                                    "extractor running before the machine starts",
                                    "bag emptied into a sealed sack before it is two thirds full"]},
    {"type": "callout", "text": "No extraction, no cut: if the extractor is not running, the machine is not started."},
)
