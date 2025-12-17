<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { socket } from '$lib/stores';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { getContext } from 'svelte';
	import { contains } from 'vega-lite';
	import { toast } from 'svelte-sonner';

	interface ModelContainer {
		model: string;
		status: string;
		is_active: boolean;
		port: number | undefined;
		device_ids: string | undefined;
		gpu_memory_utilization: number;
		tensor_parallel_size: number;
	}
	let modelContainers: ModelContainer[] = [];
	let modelContainerMapping: Map<string, number> = new Map();
	let loading = true;
	const token = localStorage.token;
	const i18n = getContext('i18n');

	const containerHandler = async (event, cb) => {
		console.log(JSON.stringify(event));
		const type = event?.data?.type ?? null;
		const data = event?.data?.data ?? null;

		if (type === 'container:model') {
			const model = data?.model;
			const index = modelContainerMapping.get(model)!;
			const container = modelContainers.at(index)!;
			container.status = data?.status;
			if (data?.status == 'start') {
				container.is_active = true;
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

		for (const [i, model] of modelList.entries()) {
			const containerInfo = await fetch(`${WEBUI_API_BASE_URL}/containers/model/${model}`, {
				method: 'GET',
				headers: {
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

			if (containerInfo) {
				modelContainers = [
					...modelContainers,
					{
						model: model,
						status: containerInfo.status,
						is_active: containerInfo.status === 'start',
						port: undefined,
						device_ids: undefined,
						gpu_memory_utilization: 0.9,
						tensor_parallel_size: 1
					}
				];

				modelContainerMapping.set(model, i);
			}
		}

		await fetch(`${WEBUI_API_BASE_URL}/containers/emit/start`, {
			method: 'PUT',
			headers: {
				Authorization: `Bearer ${token}`
			}
		});

		loading = false;
	});

	onDestroy(async () => {
		$socket?.off('container');
		await fetch(`${WEBUI_API_BASE_URL}/containers/emit/stop`, {
			method: 'PUT',
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	});

	const toggleModelContainerHandler = async (container: ModelContainer) => {
		if (container.port == undefined) {
			toast.error('Port is required');
			container.is_active = false;
			modelContainers = [...modelContainers];
			return;
		}
		let data = {
			port: container.port,
			gpus: container.device_ids ? `device=${container.device_ids?.trim()}` : undefined,
			model: container.model,
			gpu_memory_utilization: container.gpu_memory_utilization,
			tensor_parallel_size: container.tensor_parallel_size
		};
		const res = await fetch(`${WEBUI_API_BASE_URL}/containers/model/toggle`, {
			method: 'POST',
			body: JSON.stringify(data),
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		}).catch(async (e) => {
			toast.error(e);
			container.is_active = false;
		});
	};
</script>

<div>
	{$i18n.t('Containers')}
</div>
{#if loading}
	<Spinner />
{:else}
	<div class={'flex flex-col gap-y-4 text-sm'}>
		{#each modelContainers as container (container.model)}
			<div
				class="flex border-[1px] rounded-xl justify-between items-center h-20 px-4 opacity-50 hover:opacity-100 transition-all duration-300"
			>
				<div class="flex items-center gap-x-2 grow">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						height="40px"
						viewBox="0 -960 960 960"
						width="40px"
						fill="currentColor"
					>
						<path
							d="M446.67-163.67V-461l-260-150.33V-314l260 150.33Zm66.66 0 260-150.33v-298l-260 150.89v297.44ZM480-518l256.33-149L480-815.33 223-667l257 149ZM153.33-256q-15.83-9.28-24.58-24.48-8.75-15.19-8.75-33.19v-332.66q0-18 8.75-33.19 8.75-15.2 24.58-24.48l293.34-169q15.88-9 33.44-9 17.56 0 33.22 9l293.34 169q15.83 9.28 24.58 24.48 8.75 15.19 8.75 33.19v332.66q0 18-8.75 33.19-8.75 15.2-24.58 24.48L513.33-87q-15.88 9-33.44 9-17.56 0-33.22-9L153.33-256ZM480-480Z"
						/>
					</svg>
					<div class="flex flex-col">
						<div class="flex gap-2">
							<h4 class="font-bold">
								{container.model}
							</h4>
							<span class="text-xs mt-auto">
								{container.status}
							</span>
						</div>
						<span>test text</span>
					</div>
				</div>

				<div class="flex items-center gap-x-2">
					<span class="w-16">
						<label for={`${container.model}-port`}>port*</label>
						<input
							id={`${container.model}-port`}
							name="port"
							type="number"
							min="{0},"
							max="{65535},"
							placeholder="8000"
							class="w-full"
							disabled={container.is_active}
							bind:value={container.port}
							required
						/>
					</span>

					<span class="w-20">
						<label for={`${container.model}-device-ids`}>device_ids</label>
						<input
							id={`${container.model}-device-ids`}
							name="deuvce-ids"
							placeholder="0,1"
							class="w-full"
							disabled={container.is_active}
							bind:value={container.device_ids}
						/>
					</span>

					<span class="border-l-[1px] border-solid"></span>

					<span class="w-24">
						<label for={`${container.model}-gpu_memory_utilization`}>gpu_memory_utilization</label>
						<input
							id={`${container.model}-gpu_memory_utilization`}
							name="gpu_memory_utilization"
							placeholder="0.9"
							class="w-full"
							disabled={container.is_active}
							bind:value={container.gpu_memory_utilization}
						/>
					</span>

					<span class="w-24">
						<label for={`${container.model}-tensor_parallel_size`}>tensor_parallel_size</label>
						<input
							id={`${container.model}-tensor_parallel_size`}
							name="tensor_parallel_size"
							placeholder="1"
							class="w-full"
							disabled={container.is_active}
							bind:value={container.tensor_parallel_size}
						/>
					</span>

					<Switch
						bind:state={container.is_active}
						on:change={async () => {
							toggleModelContainerHandler(container);
						}}
					/>
				</div>
			</div>
		{/each}
	</div>
{/if}
