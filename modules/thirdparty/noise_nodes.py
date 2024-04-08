# Due to the current lack of maintenance for the `ComfyUI_Noise` extension,
# I have copied the code from the applied PR.
# https://github.com/BlenderNeko/ComfyUI_Noise/pull/13/files

import comfy
import torch
from comfy import sampler_helpers


class Unsampler:
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"model": ("MODEL",),
                     "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                     "end_at_step": ("INT", {"default": 0, "min": 0, "max": 10000}),
                     "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0}),
                     "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                     "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
                     "normalize": (["disable", "enable"],),
                     "positive": ("CONDITIONING",),
                     "negative": ("CONDITIONING",),
                     "latent_image": ("LATENT",),
                     }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "unsampler"

    CATEGORY = "sampling"

    def unsampler(self, model, cfg, sampler_name, steps, end_at_step, scheduler, normalize, positive, negative,
                  latent_image):
        normalize = normalize == "enable"
        device = comfy.model_management.get_torch_device()
        latent = latent_image
        latent_image = latent["samples"]

        end_at_step = min(end_at_step, steps - 1)
        end_at_step = steps - end_at_step

        noise = torch.zeros(latent_image.size(), dtype=latent_image.dtype, layout=latent_image.layout, device="cpu")
        noise_mask = None
        if "noise_mask" in latent:
            noise_mask = comfy.sampler_helpers.prepare_mask(latent["noise_mask"], noise.shape, device)

        real_model = None
        real_model = model.model

        noise = noise.to(device)
        latent_image = latent_image.to(device)

        positive = comfy.sampler_helpers.convert_cond(positive)
        negative = comfy.sampler_helpers.convert_cond(negative)

        models1, inference_memory1 = comfy.sampler_helpers.get_additional_models(positive, model.model_dtype())
        models2, inference_memory2 = comfy.sampler_helpers.get_additional_models(negative, model.model_dtype())

        comfy.model_management.load_models_gpu([model] + models1 + models2, model.memory_required(noise.shape) + inference_memory1 + inference_memory2)

        sampler = comfy.samplers.KSampler(real_model, steps=steps, device=device, sampler=sampler_name,
                                          scheduler=scheduler, denoise=1.0, model_options=model.model_options)

        sigmas = sampler.sigmas.flip(0) + 0.0001

        pbar = comfy.utils.ProgressBar(steps)

        def callback(step, x0, x, total_steps):
            pbar.update_absolute(step + 1, total_steps)

        samples = sampler.sample(noise, positive, negative, cfg=cfg, latent_image=latent_image,
                                 force_full_denoise=False, denoise_mask=noise_mask, sigmas=sigmas, start_step=0,
                                 last_step=end_at_step, callback=callback)
        if normalize:
            # technically doesn't normalize because unsampling is not guaranteed to end at a std given by the schedule
            samples -= samples.mean()
            samples /= samples.std()
        samples = samples.cpu()

        comfy.sampler_helpers.cleanup_additional_models(models1)
        comfy.sampler_helpers.cleanup_additional_models(models2)

        out = latent.copy()
        out["samples"] = samples
        return (out,)
