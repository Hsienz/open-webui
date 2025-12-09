<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { socket } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	interface ModelContainer {
		model: string;
		status: string;
		active: boolean;
	}
	let modelContainers: ModelContainer[] = [];
	let modelContainerMapping: Map<string, number> = new Map();
	let loading = true;
	const token = localStorage.token;

	const containerHandler = async (event, cb) => {
		console.log(JSON.stringify(event));
		const type = event?.data?.type ?? null;
		const data = event?.data?.data ?? null;

		const model = data?.model;
		const index = modelContainerMapping.get(model)!;
		const container = modelContainers.at(index)!;
		if (type === 'container:model') {
			container.status = data?.status;
			if (data?.status == 'start') {
				container.active = true;
			}
			modelContainers = [...modelContainers];
		}
	};
	onMount(async () => {
		loading = true;
		$socket?.on('container', containerHandler);

		const modelList = await fetch(`${WEBUI_API_BASE_URL}/containers/models`, {
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

		console.log('model list: ', modelList);
		if (!modelList) {
			loading = false;
			return;
		}

		for (const [i, model] of modelList.entries) {
			const containerInfo = await fetch(`${WEBUI_API_BASE_URL}/containers/model/${model}`)
				.then(async (res) => {
					if (!res.ok) throw await res.json();
					return res.json();
				})
				.catch((err) => {
					console.error(err);
					return null;
				});

			if (containerInfo) {
				modelContainers = [
					...modelContainers,
					{
						model: model,
						status: containerInfo.status,
						active: containerInfo.status === 'start'
					}
				];

				modelContainerMapping.set(model, i);
			}
		}
		loading = false;
	});

	onDestroy(async () => {
		$socket?.off('container');
	});

	const toggleModelContainerHandler = async (container: ModelContainer) => {
		const formData = new FormData();
		formData.set('model', container.model);
		await fetch(`${WEBUI_API_BASE_URL}/containers/model/toggle`, {
			method: 'POST',
			body: formData,
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	};
</script>

{#if loading}
	<Spinner />
{:else}
	<div>
		{#each modelContainers as container (container.model)}
			<div>
				{container.model}
				{container.status}

				<Switch
					bind:state={container.active}
					on:change={async () => {
						toggleModelContainerHandler(container);
					}}
				/>
			</div>
		{/each}
	</div>
{/if}
