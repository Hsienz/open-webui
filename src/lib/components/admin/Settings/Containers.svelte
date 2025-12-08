<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { socket } from '$lib/stores';
	import { WEBUI_BASE_URL } from '$lib/constants';

	interface ModelContainer {
		model: string;
		id: string | null;
		status: string;
	}
	let modelContainers: ModelContainer[] = [];
	let loading = true;

	const containerHandler = async (event, cb) => {
		console.log(JSON.stringify(event));
		const type = event?.data?.type ?? null;
		const data = event?.data?.data ?? null;
		if (type === 'container:model') {
		}
	};
	onMount(async () => {
		loading = true;
		$socket?.on('container', containerHandler);

		const token = localStorage.token;
		const modelList = await fetch(`${WEBUI_BASE_URL}/api/v1/containers/model/list`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				console.error(err);
				return null;
			});

		if (!modelList) {
			loading = false;
			return;
		}

		for (var model in modelList) {
			const containerInfo = await fetch(`${WEBUI_BASE_URL}/api/v1/containers/model/{model}`)
				.then(async (res) => {
					if (!res.ok) throw await res.json();
					return res.json();
				})
				.catch((err) => {
					console.error(err);
					return;
				});

			modelContainers.push({
				model,
				id: containerInfo['id'],
				status: containerInfo['status']
			});
		}
		loading = false;
	});

	onDestroy(async () => {
		$socket?.off('container');
	});
</script>

<div>
	{#each modelContainers as container (container.id)}
		{container.id}
		{container.model}
	{/each}
</div>
