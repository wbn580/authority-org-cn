import { defineCollection, z } from 'astro:content';

const articles = defineCollection({
  type: 'content',
});

export const collections = { articles };
