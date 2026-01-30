<script>
	// Svelte 5 Runes
	let tickets = $state([]);
	let syncStatus = $state(null);
	let filter = $state('pending');
	let loading = $state(true);
	
	const API_URL = 'http://localhost:8000';
	const filters = ['pending', 'approved', 'rejected', 'all'];
	
	// Derived state
	let filteredTickets = $derived(
		filter === 'all' ? tickets : tickets.filter(t => t.status === filter)
	);
	let pendingCount = $derived(tickets.filter(t => t.status === 'pending').length);
	
	// API functions
	async function fetchTickets() {
		try {
			const res = await fetch(`${API_URL}/tickets`);
			tickets = await res.json();
		} catch (err) {
			console.error('Failed to fetch tickets:', err);
		}
	}
	
	async function fetchSyncStatus() {
		try {
			const res = await fetch(`${API_URL}/sync/status`);
			syncStatus = await res.json();
		} catch (err) {
			console.error('Failed to fetch sync:', err);
		}
	}
	
	async function triggerSync() {
		await fetch(`${API_URL}/sync`, { method: 'POST' });
		await fetchSyncStatus();
		await fetchTickets();
	}
	
	async function updateTicket(ticketId, action) {
		await fetch(`${API_URL}/tickets/${ticketId}/${action}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ staff_name: 'Front Desk' })
		});
		await fetchTickets();
	}
	
	// Load on mount + auto-refresh
	$effect(() => {
		fetchTickets();
		fetchSyncStatus();
		loading = false;
		
		const interval = setInterval(() => {
			fetchTickets();
			fetchSyncStatus();
		}, 5000);
		
		return () => clearInterval(interval);
	});
	
	// Helpers
	function formatDate(dateStr) {
		return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}
	
	function getNights(checkIn, checkOut) {
		return Math.ceil((new Date(checkOut) - new Date(checkIn)) / (1000 * 60 * 60 * 24));
	}
	
	function getRoomColor(type) {
		const colors = {
			standard: 'bg-blue-100 text-blue-800',
			deluxe: 'bg-purple-100 text-purple-800',
			suite: 'bg-amber-100 text-amber-800'
		};
		return colors[type] || 'bg-gray-100 text-gray-800';
	}
	
	function getStatusColor(status) {
		const colors = {
			pending: 'bg-amber-100 text-amber-800',
			approved: 'bg-green-100 text-green-800',
			rejected: 'bg-red-100 text-red-800'
		};
		return colors[status] || 'bg-gray-100 text-gray-800';
	}
</script>

<!-- Header -->
<header class="bg-white border-b border-gray-200 sticky top-0 z-10">
	<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
		<div class="flex justify-between items-center h-16">
			<div class="flex items-center gap-3">
				<div class="w-10 h-10 bg-slate-900 rounded-lg flex items-center justify-center">
					<span class="text-white font-bold text-lg">BL</span>
				</div>
				<div>
					<h1 class="text-xl font-bold text-gray-900">Black Lotus Hotel</h1>
					<p class="text-xs text-gray-500">Voice AI Reservation System</p>
				</div>
			</div>
			
			<div class="flex items-center gap-4">
				<!-- Sync Status -->
				<div class="flex items-center gap-2 text-sm">
					{#if syncStatus?.fresh}
						<span class="flex items-center gap-1 text-green-600">
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
							Cache Fresh
						</span>
					{:else}
						<span class="flex items-center gap-1 text-amber-600">
							<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
							Stale Cache
						</span>
					{/if}
					<button onclick={triggerSync} class="p-1.5 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100" title="Trigger ERP Sync">
						<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
					</button>
				</div>
				
				<div class="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-full">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
					<span class="font-medium">{pendingCount} Pending</span>
				</div>
			</div>
		</div>
	</div>
</header>

<!-- Main Content -->
<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
	<!-- Filter Tabs -->
	<div class="flex gap-2 mb-6">
		{#each filters as f}
			<button
				onclick={() => filter = f}
				class="px-4 py-2 rounded-lg font-medium capitalize transition-colors {filter === f ? 'bg-slate-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-100'}"
			>
				{f}
				{#if f !== 'all'}
					<span class="ml-2 text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">
						{tickets.filter(t => t.status === f).length}
					</span>
				{/if}
			</button>
		{/each}
	</div>

	<!-- Tickets -->
	{#if loading}
		<div class="flex items-center justify-center h-64">
			<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
		</div>
	{:else if filteredTickets.length === 0}
		<div class="text-center py-16 bg-white rounded-xl">
			<div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
				<svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
			</div>
			<h3 class="text-lg font-medium text-gray-900">No {filter} tickets</h3>
			<p class="text-gray-500">All caught up!</p>
		</div>
	{:else}
		<div class="grid gap-4">
			{#each filteredTickets as ticket (ticket.ticket_id)}
				<div class="bg-white rounded-xl p-6 border border-gray-200 hover:shadow-lg transition-shadow">
					<div class="flex justify-between items-start">
						<div class="flex-1">
							<!-- Header -->
							<div class="flex items-center gap-3 mb-3">
								<span class="text-sm font-mono text-gray-500">{ticket.ticket_id}</span>
								<span class="px-2.5 py-1 rounded-full text-xs font-medium {getRoomColor(ticket.room_type)}">
									{ticket.room_type}
								</span>
								<span class="px-2.5 py-1 rounded-full text-xs font-medium {getStatusColor(ticket.status)}">
									{ticket.status}
								</span>
							</div>
							
							<!-- Guest Info -->
							<h3 class="text-lg font-semibold text-gray-900 mb-1">{ticket.guest_name}</h3>
							<div class="flex items-center gap-4 text-sm text-gray-600 mb-4">
								<span class="flex items-center gap-1">
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>
									{ticket.phone_number}
								</span>
								<span class="flex items-center gap-1">
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
									{ticket.guests} guests
								</span>
							</div>
							
							<!-- Dates -->
							<div class="flex items-center gap-2 text-sm bg-gray-50 rounded-lg p-3 mb-3">
								<svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
								<span class="font-medium">{formatDate(ticket.check_in)}</span>
								<span class="text-gray-400">→</span>
								<span class="font-medium">{formatDate(ticket.check_out)}</span>
								<span class="text-gray-400">({getNights(ticket.check_in, ticket.check_out)} nights)</span>
							</div>
							
							<!-- Special Requests -->
							{#if ticket.special_requests}
								<div class="text-sm text-gray-600 bg-amber-50 border border-amber-100 rounded-lg p-3">
									<span class="font-medium text-amber-800">Special Request:</span>
									{ticket.special_requests}
								</div>
							{/if}
						</div>
						
						<!-- Actions -->
						{#if ticket.status === 'pending'}
							<div class="flex flex-col gap-2 ml-4">
								<button
									onclick={() => updateTicket(ticket.ticket_id, 'approve')}
									class="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
								>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
									Approve
								</button>
								<button
									onclick={() => updateTicket(ticket.ticket_id, 'reject')}
									class="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium"
								>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
									Reject
								</button>
							</div>
						{/if}
					</div>
					
					<!-- Footer -->
					<div class="mt-4 pt-4 border-t border-gray-100 text-xs text-gray-500 flex justify-between">
						<span>Received: {new Date(ticket.created_at).toLocaleString()}</span>
						<span>Source: Voice AI</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</main>
