"use strict";
  const viewer=document.getElementById("image-viewer"),large=document.getElementById("image-large");
  for(const trigger of document.querySelectorAll(".screenshot")){trigger.addEventListener("click",()=>{const img=trigger.querySelector("img");large.src=img.src;large.alt=img.alt;document.getElementById("image-caption").textContent=trigger.parentElement.querySelector("figcaption").textContent;viewer.showModal()})}
  document.getElementById("image-close").addEventListener("click",()=>viewer.close());
  viewer.addEventListener("click",e=>{if(e.target===viewer){const rect=viewer.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)viewer.close()}});
  const navLinks=[...document.querySelectorAll(".sidebar nav a")];
  const sections=[...document.querySelectorAll("main section")];
  function updateNavigation(){let current=sections[0];for(const section of sections){if(section.getBoundingClientRect().top<=Math.min(window.innerHeight*.25,150))current=section;else break}for(const link of navLinks){const active=link.hash==="#"+current.id;link.classList.toggle("active",active);if(active)link.setAttribute("aria-current","location");else link.removeAttribute("aria-current")}}
  let navigationQueued=false;
  function queueNavigation(){if(!navigationQueued){navigationQueued=true;requestAnimationFrame(()=>{navigationQueued=false;updateNavigation()})}}
  window.addEventListener("scroll",queueNavigation,{passive:true});window.addEventListener("resize",queueNavigation);updateNavigation();
  let closedBeforePrint=null;
  window.addEventListener("beforeprint",()=>{if(closedBeforePrint===null)closedBeforePrint=[...document.querySelectorAll("details:not([open])")];for(const detail of closedBeforePrint)detail.open=true});
  window.addEventListener("afterprint",()=>{for(const detail of closedBeforePrint||[])detail.open=false;closedBeforePrint=null});
  document.getElementById("print-button").addEventListener("click",()=>window.print());
