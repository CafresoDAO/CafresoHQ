// "/dev-log" is what the label "Dev Log" invites people to type — alias it
// to the real route instead of letting it 404.
import { redirect } from '@sveltejs/kit';

export function load() {
  redirect(308, '/blog');
}
