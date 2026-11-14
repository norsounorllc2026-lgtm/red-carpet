// =============================================================================
//  RED CARPET — Wix page code for the "red-carpet" page
// =============================================================================
//  WHERE THIS GOES
//    Wix Editor -> open the red-carpet page -> Dev Mode -> code panel at the
//    bottom ("red-carpet" page code) -> replace everything with this file.
//    Needs public/agoShell.js.
//
//  WHAT IT DOES
//    Connects the HTML embed with the ID #redCarpet: back button,
//    "More from AGO" links and members (all handled by public/agoShell.js).
// =============================================================================
import { connectEmbed } from 'public/agoShell';

$w.onReady(function () {
  connectEmbed($w, '#redCarpet');
});
